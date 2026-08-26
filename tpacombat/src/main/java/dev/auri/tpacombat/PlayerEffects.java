package dev.auri.tpacombat;

import net.minecraft.entity.effect.StatusEffectInstance;
import net.minecraft.entity.effect.StatusEffects;
import net.minecraft.entity.projectile.thrown.EnderPearlEntity;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.network.ServerPlayerEntity;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.stat.Stats;

import java.util.ArrayList;
import java.util.List;

/** Applies the General-tab settings that need per-tick or per-death enforcement. */
public final class PlayerEffects {

    /**
     * Phantoms are gated on each player's own {@code timeSinceRest} statistic: the spawner skips a
     * player when {@code random.nextInt(clamp(stat, 1, MAX)) < 72000}. Holding the stat at zero
     * therefore suppresses phantoms for that player alone, with no mixin and no effect on anyone
     * else. The trade-off is that their "time since last rest" statistic stays pinned at zero.
     */
    private static final int PHANTOM_STAT_RESET_INTERVAL = 200;

    private final PlayerDataStore store;
    private int tickCounter;

    public PlayerEffects(PlayerDataStore store) {
        this.store = store;
    }

    public void onEndTick(MinecraftServer server) {
        if (++tickCounter < PHANTOM_STAT_RESET_INTERVAL) {
            return;
        }
        tickCounter = 0;

        for (ServerPlayerEntity player : server.getPlayerManager().getPlayerList()) {
            PlayerProfile profile = store.get(player.getUuid());
            if (!profile.phantomSpawning) {
                player.getStatHandler().setStat(player,
                        Stats.CUSTOM.getOrCreateStat(Stats.TIME_SINCE_REST), 0);
            }
            applyNightVision(player, profile);
        }
    }

    /**
     * Re-applied on a timer rather than once, so it survives death, dimension changes and milk.
     * Ambient with no particles or icon so it does not clutter the HUD.
     */
    private static void applyNightVision(ServerPlayerEntity player, PlayerProfile profile) {
        boolean has = player.hasStatusEffect(StatusEffects.NIGHT_VISION);
        if (profile.nightVision) {
            if (!has) {
                player.addStatusEffect(new StatusEffectInstance(StatusEffects.NIGHT_VISION,
                        StatusEffectInstance.INFINITE, 0, true, false, false));
            }
        } else if (has) {
            StatusEffectInstance active = player.getStatusEffect(StatusEffects.NIGHT_VISION);
            // Only clear the infinite one this mod applied; leave potions and beacons alone.
            if (active != null && active.isInfinite() && active.isAmbient()) {
                player.removeStatusEffect(StatusEffects.NIGHT_VISION);
            }
        }
    }

    /** Called on death: discards the player's in-flight pearls when they asked for that. */
    public void onDeath(MinecraftServer server, ServerPlayerEntity player) {
        if (store.get(player.getUuid()).keepEnderPearlsOnDeath) {
            return;
        }
        List<EnderPearlEntity> doomed = new ArrayList<>();
        for (ServerWorld world : server.getWorlds()) {
            for (var entity : world.iterateEntities()) {
                if (entity instanceof EnderPearlEntity pearl && pearl.getOwner() == player) {
                    doomed.add(pearl);
                }
            }
        }
        for (EnderPearlEntity pearl : doomed) {
            pearl.discard();
        }
    }
}
