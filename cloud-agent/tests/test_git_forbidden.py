# -*- coding: utf-8 -*-
"""Yikici git islemleri kod duzeyinde reddedilmeli."""
import re
from g17cloud.github_core import FORBIDDEN


def _blocked(cmd):
    return any(p.search(cmd) for p in FORBIDDEN)


def check_force_push_blocked():
    for cmd in ("push origin main --force",
                "push origin main --force-with-lease",
                "push -f origin main"):
        assert _blocked(cmd), "engellenmedi: %s" % cmd


def check_history_rewrite_blocked():
    for cmd in ("reset --hard origin/main", "filter-branch --tree-filter x",
                "filter-repo --path a", "branch -D main", "remote remove origin"):
        assert _blocked(cmd), "engellenmedi: %s" % cmd


def check_normal_ops_allowed():
    for cmd in ("push origin main", "commit -q -m mesaj", "fetch --quiet origin main",
                "merge --ff-only origin/main", "worktree add --detach /tmp/x origin/main"):
        assert not _blocked(cmd), "gereksiz engellendi: %s" % cmd
