"""Knowledge graph service for Brain V3 Phase 1 (non-executable)."""

from __future__ import annotations

import hashlib
from collections import deque
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from .confidence import assert_not_auto_verified, merge_confidence, merge_confidence_category
from .errors import ConflictError, LimitExceededError, ValidationError
from .limits import BrainV3Limits
from .models import ConflictRecord, Entity, Relation, new_id, normalize_key, utc_now_iso
from .validation import build_entity, build_relation


class GraphService:
    """Bounded graph operations over entities and relations."""

    def __init__(self, repo: Any, limits: BrainV3Limits | None = None) -> None:
        self._repo = repo
        self._limits = limits or BrainV3Limits()

    def _ensure_writable(self) -> None:
        if getattr(self._repo, "read_only", False):
            raise ValidationError("repository is read-only")

    def create_entity(self, data: Mapping[str, Any]) -> Entity:
        self._ensure_writable()
        if self._repo.count_entities() >= self._limits.max_entities:
            raise LimitExceededError("max_entities exceeded")
        entity = build_entity(data, self._limits)
        existing = self._repo.find_entity_by_canonical(entity.entity_type, entity.canonical_name)
        if existing is not None and existing.status == "active":
            raise ConflictError("entity already exists")
        return self._repo.create_entity(entity)

    def update_entity(self, entity_id: str, updates: Mapping[str, Any]) -> Entity:
        self._ensure_writable()
        current = self.get_entity(entity_id)
        merged = {**current.to_dict(), **dict(updates), "id": entity_id}
        if "confidence_category" in updates:
            new_cat = str(updates["confidence_category"])
            if new_cat == "verified":
                assert_not_auto_verified(current.confidence_category)
        entity = build_entity(merged, self._limits)
        entity.updated_at = utc_now_iso()
        if "confidence" in updates:
            entity.confidence = merge_confidence(current.confidence, entity.confidence, limits=self._limits)
        if "confidence_category" in updates:
            entity.confidence_category = merge_confidence_category(
                current.confidence_category,
                entity.confidence_category,
            )
        return self._repo.update_entity(entity)

    def archive_entity(self, entity_id: str) -> Entity:
        return self.update_entity(entity_id, {"status": "archived"})

    def get_entity(self, entity_id: str) -> Entity:
        return self._repo.get_entity(entity_id)

    def list_entities(
        self,
        *,
        entity_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Entity]:
        bounded = min(max(1, limit), self._limits.max_batch_size)
        return self._repo.list_entities(
            entity_type=entity_type,
            status=status,
            limit=bounded,
            offset=max(0, offset),
        )

    def create_relation(self, data: Mapping[str, Any]) -> Relation:
        self._ensure_writable()
        if self._repo.count_relations() >= self._limits.max_relations:
            raise LimitExceededError("max_relations exceeded")
        relation = build_relation(data, self._limits)
        self.get_entity(relation.source_entity_id)
        self.get_entity(relation.target_entity_id)
        return self._repo.create_relation(relation)

    def remove_relation(self, relation_id: str) -> Relation:
        self._ensure_writable()
        relation = self._repo.get_relation(relation_id)
        relation.status = "archived"
        relation.updated_at = utc_now_iso()
        return self._repo.update_relation(relation)

    def find_neighbors(
        self,
        entity_id: str,
        *,
        limit: int = 100,
    ) -> List[Tuple[Entity, Relation]]:
        self.get_entity(entity_id)
        bounded = min(max(1, limit), self._limits.max_batch_size)
        return self._repo.neighbors(entity_id, limit=bounded)

    def traverse(
        self,
        start_id: str,
        *,
        max_depth: Optional[int] = None,
        max_nodes: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Cycle-safe bounded BFS traversal from ``start_id``."""
        self.get_entity(start_id)
        depth_limit = max_depth if max_depth is not None else self._limits.max_traversal_depth
        node_limit = max_nodes if max_nodes is not None else self._limits.max_traversal_nodes
        edge_limit = self._limits.max_traversal_edges

        visited: Set[str] = {start_id}
        nodes: List[Entity] = [self.get_entity(start_id)]
        edges: List[Relation] = []
        queue: deque[tuple[str, int]] = deque([(start_id, 0)])

        while queue and len(nodes) < node_limit and len(edges) < edge_limit:
            current_id, depth = queue.popleft()
            if depth >= depth_limit:
                continue
            for neighbor, relation in self.find_neighbors(current_id, limit=edge_limit):
                if relation.id not in {e.id for e in edges}:
                    edges.append(relation)
                if len(edges) >= edge_limit:
                    break
                if neighbor.id in visited:
                    continue
                if len(nodes) >= node_limit:
                    break
                visited.add(neighbor.id)
                nodes.append(neighbor)
                queue.append((neighbor.id, depth + 1))

        return {
            "start_id": start_id,
            "nodes": nodes,
            "edges": edges,
            "depth_limit": depth_limit,
            "node_limit": node_limit,
            "edge_limit": edge_limit,
        }

    def find_path(
        self,
        source_id: str,
        target_id: str,
        *,
        max_depth: Optional[int] = None,
    ) -> List[Relation]:
        """Shortest active relation path between two entities."""
        if source_id == target_id:
            return []
        self.get_entity(source_id)
        self.get_entity(target_id)
        depth_limit = max_depth if max_depth is not None else self._limits.max_traversal_depth

        queue: deque[str] = deque([source_id])
        parent: Dict[str, Optional[str]] = {source_id: None}
        relation_by_target: Dict[str, Relation] = {}

        while queue:
            current = queue.popleft()
            depth = 0
            node = current
            while parent.get(node) is not None and depth < depth_limit:
                node = parent[node]  # type: ignore[assignment]
                depth += 1
            if depth >= depth_limit:
                continue
            for neighbor, relation in self.find_neighbors(current, limit=self._limits.max_batch_size):
                if relation.status != "active":
                    continue
                if neighbor.id in parent:
                    continue
                parent[neighbor.id] = current
                relation_by_target[neighbor.id] = relation
                if neighbor.id == target_id:
                    path: List[Relation] = []
                    walk: Optional[str] = target_id
                    while walk and walk != source_id:
                        path.append(relation_by_target[walk])
                        walk = parent[walk]
                    path.reverse()
                    return path
                queue.append(neighbor.id)
        return []

    def find_duplicates(self, *, entity_type: Optional[str] = None) -> List[List[Entity]]:
        """Find exact canonical duplicates among active entities."""
        entities = self.list_entities(entity_type=entity_type, status="active", limit=self._limits.max_batch_size)
        groups: Dict[tuple[str, str], List[Entity]] = {}
        for entity in entities:
            key = (entity.entity_type, entity.canonical_name)
            groups.setdefault(key, []).append(entity)
        return [group for group in groups.values() if len(group) > 1]

    def find_alias_candidates(self, *, entity_type: Optional[str] = None) -> List[Tuple[Entity, Entity]]:
        """Detect active entities sharing display names or aliases."""
        entities = self.list_entities(entity_type=entity_type, status="active", limit=self._limits.max_batch_size)
        by_label: Dict[str, List[Entity]] = {}
        for entity in entities:
            labels = {normalize_key(entity.display_name, max_len=self._limits.max_name_len)}
            labels.update(normalize_key(alias, max_len=self._limits.max_name_len) for alias in entity.aliases)
            for label in labels:
                by_label.setdefault(label, []).append(entity)
        pairs: List[Tuple[Entity, Entity]] = []
        seen: Set[tuple[str, str]] = set()
        for bucket in by_label.values():
            if len(bucket) < 2:
                continue
            for i, left in enumerate(bucket):
                for right in bucket[i + 1 :]:
                    if left.id == right.id:
                        continue
                    if left.canonical_name == right.canonical_name:
                        continue
                    key = tuple(sorted((left.id, right.id)))
                    if key in seen:
                        continue
                    seen.add(key)
                    pairs.append((left, right))
        return pairs

    def record_conflict(
        self,
        entity_id: str,
        field: str,
        value_a: str,
        value_b: str,
        *,
        source_a: Optional[str] = None,
        source_b: Optional[str] = None,
    ) -> ConflictRecord:
        self._ensure_writable()
        self.get_entity(entity_id)
        conflict = ConflictRecord(
            id=new_id("conf"),
            entity_id=entity_id,
            field=field,
            value_a=value_a,
            value_b=value_b,
            source_a=source_a,
            source_b=source_b,
            created_at=utc_now_iso(),
            status="open",
            requires_confirmation=True,
        )
        return self._repo.create_conflict(conflict)

    def list_conflicts(
        self,
        *,
        entity_id: Optional[str] = None,
        status: str = "open",
        limit: int = 100,
        offset: int = 0,
    ) -> List[ConflictRecord]:
        bounded = min(max(1, limit), self._limits.max_batch_size)
        return self._repo.list_conflicts(
            entity_id=entity_id,
            status=status,
            limit=bounded,
            offset=max(0, offset),
        )

    @staticmethod
    def canonical_fingerprint(entity_type: str, canonical_name: str) -> str:
        payload = f"{entity_type}\n{normalize_key(canonical_name)}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
