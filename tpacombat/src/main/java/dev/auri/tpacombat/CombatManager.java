package dev.auri.tpacombat;

import net.minecraft.entity.Entity;
import net.minecraft.entity.LivingEntity;
import net.minecraft.entity.damage.DamageSource;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.network.ServerPlayerEntity;
import net.minecraft.server.world.ServerWorld;

import java.util.Iterator;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/** PvP combat tagging and the combat-log punishment. */
public final class CombatManager {

    private final Map<UUID, Long> tagged = new ConcurrentHashMap<>();
    private final Map<UUID, Hit> lastAttacker = new ConcurrentHashMap<>();
    private volatile boolean serverStopping;
    private int tickCounter;
    private PlayerDataStore store;

    public void setStore(PlayerDataStore store) {
        this.store = store;
    }

    /** Combat alerts are opt-out per player; missing store means "not loaded yet", so allow. */
    private boolean wantsCombatAlerts(ServerPlayerEntity player) {
        return store == null || store.get(player.getUuid()).combatAlerts;
    }

    private static long tagDurationMillis() {
        return Config.get().combat.tagSeconds * 1000L;
    }

    public boolean isTagged(ServerPlayerEntity player) {
        Long expiresAt = tagged.get(player.getUuid());
        if (expiresAt == null) {
            return false;
        }
        if (expiresAt <= System.currentTimeMillis()) {
            tagged.remove(player.getUuid());
            return false;
        }
        return true;
    }

    public int remainingSeconds(ServerPlayerEntity player) {
        Long expiresAt = tagged.get(player.getUuid());
        if (expiresAt == null) {
            return 0;
        }
        long remaining = expiresAt - System.currentTimeMillis();
        return remaining <= 0L ? 0 : (int) Math.ceil(remaining / 1000.0);
    }

    public void tag(ServerPlayerEntity player) {
        if (player.isCreative() || player.isSpectator()) {
            return;
        }
        boolean alreadyTagged = isTagged(player);
        tagged.put(player.getUuid(), System.currentTimeMillis() + tagDurationMillis());
        if (!alreadyTagged && wantsCombatAlerts(player)) {
            Messages.actionBar(player, Messages.combatBar(Config.get().combat.tagSeconds));
        }
    }

    public void sendInCombat(ServerPlayerEntity player) {
        Messages.actionBar(player, Messages.inCombat(remainingSeconds(player)));
    }

    /** Refreshes the action-bar countdown once a second and expires finished tags. */
    public void onEndTick(MinecraftServer server) {
        if (++tickCounter < 20) {
            return;
        }
        tickCounter = 0;

        long now = System.currentTimeMillis();
        Iterator<Map.Entry<UUID, Long>> it = tagged.entrySet().iterator();
        while (it.hasNext()) {
            Map.Entry<UUID, Long> entry = it.next();
            ServerPlayerEntity player = server.getPlayerManager().getPlayer(entry.getKey());
            if (entry.getValue() <= now) {
                it.remove();
                if (player != null && wantsCombatAlerts(player)) {
                    Messages.actionBar(player, Messages.combatExpired());
                }
                continue;
            }
            if (player == null || !wantsCombatAlerts(player)) {
                continue;
            }
            int seconds = (int) Math.ceil((entry.getValue() - now) / 1000.0);
            Messages.actionBar(player, Messages.combatBar(seconds));
        }

        long attackerCutoff = now - tagDurationMillis();
        lastAttacker.values().removeIf(hit -> hit.time() < attackerCutoff);
    }

    /** Only direct player attackers tag: {@code getAttacker} already resolves arrow/trident shooters. */
    private static ServerPlayerEntity resolveAttacker(DamageSource source) {
        Entity entity = source.getAttacker();
        return entity instanceof ServerPlayerEntity player ? player : null;
    }

    /**
     * Fires even when the hit was blocked by a shield, which matches the original's use of
     * LivingHurtEvent -- shield-tanking a hit still puts both players in combat.
     */
    public void onAfterDamage(LivingEntity entity, DamageSource source) {
        if (!(entity instanceof ServerPlayerEntity victim)) {
            return;
        }
        ServerPlayerEntity attacker = resolveAttacker(source);
        if (attacker == null || attacker.getUuid().equals(victim.getUuid())) {
            return;
        }
        tag(attacker);
        tag(victim);
        lastAttacker.put(victim.getUuid(),
                new Hit(attacker.getUuid(), attacker.getGameProfile().name(), System.currentTimeMillis()));
    }

    public void onAfterDeath(LivingEntity entity, DamageSource source) {
        if (!(entity instanceof ServerPlayerEntity victim)) {
            return;
        }
        tagged.remove(victim.getUuid());
        lastAttacker.remove(victim.getUuid());

        ServerPlayerEntity killer = resolveAttacker(source);
        if (killer != null
                && !killer.getUuid().equals(victim.getUuid())
                && Config.get().combat.untagOnKill
                && tagged.remove(killer.getUuid()) != null) {
            if (wantsCombatAlerts(killer)) {
                Messages.actionBar(killer, Messages.combatUntagKill());
            }
        }
    }

    /**
     * Runs while the player is still in the world, so the kill produces a normal death: inventory
     * drops where they logged out and the kill is credited to whoever hit them last.
     */
    public void onDisconnect(ServerPlayerEntity player) {
        boolean wasTagged = isTagged(player);
        tagged.remove(player.getUuid());
        Hit hit = lastAttacker.remove(player.getUuid());

        if (!wasTagged || isDeadOrDying(player)) {
            return;
        }
        if (serverStopping || !Config.get().combat.punishCombatLog) {
            return;
        }
        MinecraftServer server = player.getEntityWorld().getServer();
        if (server == null) {
            return;
        }

        ServerPlayerEntity killer = hit == null ? null : server.getPlayerManager().getPlayer(hit.player());
        ServerWorld world = player.getEntityWorld();

        player.timeUntilRegen = 0;
        if (killer != null) {
            player.damage(world, world.getDamageSources().playerAttack(killer), Float.MAX_VALUE);
        }
        if (!isDeadOrDying(player)) {
            player.timeUntilRegen = 0;
            player.damage(world, world.getDamageSources().genericKill(), Float.MAX_VALUE);
        }

        if (Config.get().combat.broadcastCombatLog) {
            String name = player.getGameProfile().name();
            Messages.broadcast(server, hit != null
                    ? Messages.combatLogBroadcastKiller(name, hit.name())
                    : Messages.combatLogBroadcast(name));
        }
    }

    private static boolean isDeadOrDying(ServerPlayerEntity player) {
        return player.isDead() || player.getHealth() <= 0.0F;
    }

    public void onServerStarting() {
        serverStopping = false;
        tagged.clear();
        lastAttacker.clear();
    }

    /** Set before players are kicked so a restart never counts as combat logging. */
    public void onServerStopping() {
        serverStopping = true;
    }

    private record Hit(UUID player, String name, long time) {
    }
}
