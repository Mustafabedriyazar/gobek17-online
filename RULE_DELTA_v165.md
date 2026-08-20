# OKEY17 / GÖBEK17 — KANONİK DELTA v165

**Taban:** `gobek17-164-account-security-moderation`
**Build:** `gobek17-165-recovery-chat-profile-ops`

## Gameplay

**KANONİK OYUN KURALI DEĞİŞİKLİĞİ YOKTUR.**

v152 immutable meld / max-two process, v153 side-take, v157 illegal middle-process penalty, v160 end-overlay priority and all later gameplay/UI guarantees remain in force.

## Platform additions

1. Backup-code account recovery and authenticated password/code rotation.
2. Server-authoritative room chat; sender identity/time are server-owned.
3. `muteUntil` now blocks actual chat sends while leaving gameplay available unless banned.
4. Chat reports can carry `messageId`; moderators can remove a server chat message.
5. Durable player profile + match statistics.
6. Private wallet foundation with idempotent admin operations; **no automatic gameplay economy settlement** is introduced.
