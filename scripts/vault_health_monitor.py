#!/usr/bin/env python3
"""VaultHealthMonitor — fast health scoring for SecondBrainForge client vaults.

Single-pass scan: reads each file once, caches all metadata, then computes scores.
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
from datetime import datetime


class VaultHealthMonitor:
    """Fast vault health scanner with cached single-pass reads."""

    LINK_RE = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')
    ALIAS_RE = re.compile(r'^aliases:\s*\[([^\]]*)\]', re.MULTILINE)
    STATUS_RE = re.compile(r'#?status[\s:/]+(\S+)')

    def __init__(self, vault_path: Path):
        self.vault = Path(vault_path)
        self.notes = {}          # name -> {content, stem, path}
        self.metrics = {}
    
    def scan(self) -> dict:
        """Single-pass scan: read all files, cache metadata."""
        # Phase 1: read all markdown files into memory
        paths = list(self.vault.rglob("*.md"))
        total = len(paths)
        
        self.metrics = {
            "total_files": total,
            "empty_files": 0,
            "broken_links": 0,
            "total_links": 0,
            "stubs": 0,
            "evergreens": 0,
            "gateways": 0,
            "orphans": 0,
            "health_score": 0.0,
            "grade": "F",
        }
        
        if total == 0:
            self.metrics["details"] = ["No markdown files found"]
            return self.metrics
        
        for p in paths:
            try:
                text = p.read_text(encoding="utf-8")
            except:
                continue
            stem = p.stem
            self.notes[stem] = {"content": text, "path": str(p), "stem": stem}
        
        # Phase 2: detect aliases from cached content
        self._build_alias_index()
        
        # Phase 3: analyze each note (single pass over cached data)
        for stem, data in self.notes.items():
            self._analyze_note(stem, data)
        
        # Phase 4: orphaned notes check
        self._count_orphans()
        
        # Phase 5: score
        self._calculate_score()
        return self.metrics
    
    def _build_alias_index(self) -> None:
        """Add aliases to the notes dict so links resolve."""
        alias_to_stem = {}
        for stem, data in list(self.notes.items()):
            m = self.ALIAS_RE.search(data["content"])
            if m:
                aliases = [a.strip().strip("'\"") for a in m.group(1).split(",")]
                for a in aliases:
                    if a and a not in self.notes:
                        alias_to_stem[a] = stem
        self.alias_to_stem = alias_to_stem
        self.all_note_names = set(self.notes.keys()) | set(self.alias_to_stem.keys())
    
    def _analyze_note(self, stem: str, data: dict) -> None:
        content = data["content"]
        
        # Empty body check
        body_start = content.find("---", 2) if content.startswith("---") else 0
        body = content[body_start+3:] if body_start > 0 else content
        if len(body.strip()) < 20:
            self.metrics["empty_files"] += 1
        
        # Status detection
        status = self.STATUS_RE.search(content)
        status_str = status.group(1) if status else ""
        if status_str in ("seedling", "sprout"):
            self.metrics["stubs"] += 1
        elif status_str == "evergreen":
            self.metrics["evergreens"] += 1
        elif "gateway" in content[:500].lower() or "status/gateway" in content:
            self.metrics["gateways"] += 1
        
        # Link extraction
        links = self.LINK_RE.findall(content)
        self.metrics["total_links"] += len(links)
        for link_text in links:
            target = link_text.strip()
            if target and target not in self.all_note_names:
                self.metrics["broken_links"] += 1
    
    def _count_orphans(self) -> None:
        """Orphan = never referenced by another note (excluding special pages)."""
        referenced = set()
        for data in self.notes.values():
            for link in self.LINK_RE.findall(data["content"]):
                # Strip aliases and anchor links
                target = link.strip().split("#")[0].split("|")[0].strip()
                if target in self.notes:
                    referenced.add(target)
        
        special = {"Home", "README", "index", "Session Handoff", "Session Restart Handoff"}
        for stem in self.notes:
            if stem not in referenced and not any(stem.startswith(s) for s in special):
                self.metrics["orphans"] += 1
    
    def _calculate_score(self) -> None:
        total = self.metrics["total_files"]
        if total == 0:
            self.metrics["health_score"] = 0.0
            return
        
        # Weights
        w_links = 30 * max(0, 1 - (self.metrics["broken_links"] / max(self.metrics["total_links"], 1)) * 5)
        w_stubs = 25 * max(0, 1 - (self.metrics["stubs"] / total) * 2)
        w_orphans = 20 * max(0, 1 - (self.metrics["orphans"] / total) * 3)
        w_empty = 15 * max(0, 1 - (self.metrics["empty_files"] / total) * 10)
        w_evergreen = 10 * ((self.metrics["evergreens"] + self.metrics["gateways"]) / total)
        
        score = w_links + w_stubs + w_orphans + w_empty + w_evergreen
        self.metrics["health_score"] = round(min(100, max(0, score)), 1)
        self.metrics["grade"] = self._grade(score)
        
        self.metrics["details"] = [
            f"Total files: {total}",
            f"Broken links: {self.metrics['broken_links']} / {self.metrics['total_links']}",
            f"Stubs: {self.metrics['stubs']} ({round(self.metrics['stubs']/total*100,1)}%)",
            f"Evergreens: {self.metrics['evergreens']} ({round(self.metrics['evergreens']/total*100,1)}%)",
            f"Gateways: {self.metrics['gateways']}",
            f"Orphans: {self.metrics['orphans']}",
            f"Empty files: {self.metrics['empty_files']}",
            f"Score: {self.metrics['health_score']}/100 ({self.metrics['grade']})",
        ]
    
    def _grade(self, score: float) -> str:
        if score >= 90: return "A"
        if score >= 80: return "B"
        if score >= 70: return "C"
        if score >= 60: return "D"
        return "F"
    
    def print_report(self) -> None:
        print("=" * 50)
        print("SECONDBRAINFORGE VAULT HEALTH REPORT")
        print("=" * 50)
        for d in self.metrics.get("details", []):
            print(f"  {d}")
        print("=" * 50)
    
    def to_json(self) -> str:
        data = dict(self.metrics)
        data["timestamp"] = datetime.now().isoformat()
        return json.dumps(data, indent=2)


def main():
    import argparse
    p = argparse.ArgumentParser(description="SecondBrainForge Vault Health Monitor")
    p.add_argument("--vault", type=Path, required=True)
    p.add_argument("--json", action="store_true")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    
    monitor = VaultHealthMonitor(args.vault)
    monitor.scan()
    
    if args.json:
        output = monitor.to_json()
    else:
        monitor.print_report()
        output = None
    
    if args.output:
        args.output.write_text(monitor.to_json(), encoding="utf-8")
        print(f"Written to {args.output}")
    elif output:
        print(output)
    
    return 0 if monitor.metrics["health_score"] >= 70 else 1


if __name__ == "__main__":
    sys.exit(main())
