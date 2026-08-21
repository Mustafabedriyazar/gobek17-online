# G17 Cloud Agent v2 — surekli calisan release controller.
# Telefon/Termux bagimliligi YOKTUR. Railway ikinci servis, Linux container
# veya herhangi bir cloud runner uzerinde ayni imaj calisir.
FROM python:3.12-slim

# git: repo clone/worktree/commit icin ZORUNLU (deterministik GitHub Core kullanir)
# ca-certificates: GitHub/Railway HTTPS dogrulamasi
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Node + npm: hedef projenin (GOBEK17) testleri node ile kosulur; ayrica
# resmi Claude Code CLI npm ile kurulur (abonelik kimligi bunun uzerinden gider).
COPY --from=node:22-bookworm-slim /usr/local/ /usr/local/
RUN node --version && npm --version \
 && npm install -g @anthropic-ai/claude-code \
 && npm cache clean --force

WORKDIR /app
COPY g17cloud/ /app/g17cloud/
COPY guards/   /app/guards/
COPY tests/    /app/tests/

# Kalici durum: Railway volume buraya baglanir (task state + artifact + lock).
# CLAUDE_CONFIG_DIR kalici volume altinda: Railway restart/deploy sonrasi
# Claude CLI yapilandirmasi ve onboarding durumu kaybolmaz.
# NOT: abonelik token'i (CLAUDE_CODE_OAUTH_TOKEN) imaja GOMULMEZ; calisma
# aninda ortam degiskeni olarak verilir ve hicbir yere yazilmaz.
# NOT: CLAUDE_CONFIG_DIR Anthropic tarafindan BELGELENMEMISTIR. Kalici oturum icin
# belgelenmis konum ~/.claude oldugundan G17_CLAUDE_HOME de volume altindadir;
# ai_worker cocuk surece HOME olarak bunu verir.
ENV G17_STATE_DIR=/data/g17 \
    CLAUDE_CONFIG_DIR=/data/g17/claude \
    G17_CLAUDE_HOME=/data/g17/claude-home \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN mkdir -p /data/g17/claude /data/g17/claude-home/.claude \
 && chmod 700 /data/g17/claude /data/g17/claude-home /data/g17/claude-home/.claude

# Kok olmayan kullanici — AI ve testler ayricalikli kullanici olarak calismaz.
RUN useradd -m -u 10001 g17 && chown -R g17:g17 /app /data && chmod 700 /data/g17/claude /data/g17/claude-home
USER g17

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request,os,sys; \
url='http://127.0.0.1:%s/health'%os.environ.get('PORT','8080'); \
sys.exit(0 if urllib.request.urlopen(url,timeout=4).status==200 else 1)"

CMD ["python3", "-m", "g17cloud"]
