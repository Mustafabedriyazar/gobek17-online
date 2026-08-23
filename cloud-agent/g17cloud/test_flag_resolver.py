import os, sys, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from g17cloud import ai_worker as aiw
from g17cloud.ai_worker import (AIError, ClaudeCLIProvider,
                                g17_probe_ok, g17_resolve_tool_flags)

def t(name, cond):
    print(("PASS" if cond else "FAIL"), "-", name)
    return bool(cond)

ok = True
H_LEGACY = "Usage: claude\n  --tools <list>\n  --disallowedTools <list>\n"
a, d = g17_resolve_tool_flags(H_LEGACY)
ok &= t("1 legacy: --tools + --disallowedTools", a == "--tools" and d == "--disallowedTools")

H_CAMEL = "Options:\n  --allowedTools <t>  izin\n  --disallowedTools <t>  yasak\n"
a, d = g17_resolve_tool_flags(H_CAMEL)
ok &= t("2 camelCase: --allowedTools + --disallowedTools", a == "--allowedTools" and d == "--disallowedTools")

H_KEBAB = "Options:\n  --allowed-tools <t>\n  --disallowed-tools <t>\n"
a, d = g17_resolve_tool_flags(H_KEBAB)
ok &= t("3 kebab: --allowed-tools + --disallowed-tools", a == "--allowed-tools" and d == "--disallowed-tools")

H_PROSE = ("Options:\n  --allowedTools <t>  arac izin listesi\n"
           "      Use this instead of deprecated --tools which was removed.\n"
           "  --disallowedTools <t>\n")
a, d = g17_resolve_tool_flags(H_PROSE)
ok &= t("4 prose tuzagi: deprecated --tools secilmez", a == "--allowedTools")

H_NOALLOW = "Options:\n  --disallowedTools <t>\n  --print\n"
try:
    g17_resolve_tool_flags(H_NOALLOW); ok &= t("5 allow eksik: MISMATCH", False)
except AIError as ex:
    ok &= t("5 allow eksik: MISMATCH", "CLI_CAPABILITY_MISMATCH" in str(ex))

H_NODENY = "Options:\n  --allowedTools <t>\n  --print\n"
try:
    g17_resolve_tool_flags(H_NODENY); ok &= t("6 deny eksik: MISMATCH", False)
except AIError as ex:
    ok &= t("6 deny eksik: MISMATCH", "CLI_CAPABILITY_MISMATCH" in str(ex))

ok &= t("6b probe: eksikte False, tamda True",
        g17_probe_ok(H_NODENY) is False and g17_probe_ok(H_CAMEL) is True)

def argv_for(help_text):
    cfg = types.SimpleNamespace(
        ai_auth_mode=lambda: "TEST_NONE", ai_key=lambda: "",
        claude_oauth=lambda: "", subscription_available=lambda: False,
        claude_home="", claude_config_dir="")
    prov = ClaudeCLIProvider(cfg)
    prov.available = lambda: True
    prov._help = lambda: help_text
    seen = {}
    real = aiw.subprocess.run
    def fake(argv, **kw):
        seen["argv"] = list(argv)
        return types.SimpleNamespace(stdout="", stderr="", returncode=0)
    aiw.subprocess.run = fake
    try:
        prov.run("sys", "prompt", timeout=5, cwd="/tmp")
    finally:
        aiw.subprocess.run = real
    return seen["argv"]

av = argv_for(H_CAMEL)
ok &= t("7 argv camel: allow/deny resolver'dan",
        "--allowedTools" in av and "--disallowedTools" in av and "--tools" not in av)
av = argv_for(H_KEBAB)
ok &= t("7b argv kebab: allow/deny resolver'dan",
        "--allowed-tools" in av and "--disallowed-tools" in av
        and "--allowedTools" not in av and "--tools" not in av)

src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
aiw_src = open(os.path.join(src_dir, "ai_worker.py"), encoding="utf-8").read()
pipe_src = open(os.path.join(src_dir, "pipeline.py"), encoding="utf-8").read()
maint_src = open(os.path.join(src_dir, "maintenance.py"), encoding="utf-8").read()
ok &= t("8 tek kaynak: pipeline+maintenance ortak AIWorker, claude argv tek yerde",
        "AIWorker(cfg" in pipe_src and "AIWorker(cfg" in maint_src
        and pipe_src.count('"--print"') == 0 and maint_src.count('"--print"') == 0
        and aiw_src.count('"--print", allow_flag') == 1
        and aiw_src.count('tf = "--tools"') == 0
        and aiw_src.count('"--print", "--tools"') == 0)

print("TOPLAM:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
