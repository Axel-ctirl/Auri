package dev.auri.tpacombat;

import net.minecraft.entity.effect.StatusEffectInstance;
import net.minecraft.entity.effect.StatusEffects;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.network.ServerPlayerEntity;
import net.minecraft.stat.Stats;

/** Applies the General-tab settings that need per-tick or per-death enforcement. */
public final class PlayerEffects {

    /** Night vision is cheap to check and needs to feel instant, so it runs once a second. */
    private static final int EFFECT_INTERVAL = 20;

    /**
     * Phantoms are gated on each player's own {@code timeSinceRest} statistic: the spawner skips a
     * player when {@code random.nextInt(clamp(stat, 1, MAX)) < 72000}. Holding the stat at zero
     * therefore suppresses phantoms for that player alone, with no mixin and no effect on anyone
     * else. Writing a statistic is comparatively expensive and the threshold is an hour of game
     * time, so this runs far less often than the effect pass.
     */
    private static final int PHANTOM_INTERVAL = 200;

    private final PlayerDataStore store;
    private int effectTicks;
    private int phantomTicks;

    public PlayerEffects(PlayerDataStore store) {
        this.store = store;
    }

    public void onEndTick(MinecraftServer server) {
        boolean doEffects = ++effectTicks >= EFFECT_INTERVAL;
        boolean doPhantoms = ++phantomTicks >= PHANTOM_INTERVAL;
        if (!doEffects && !doPhantoms) {
            return;
        }
        if (doEffects) {
            effectTicks = 0;
        }
        if (doPhantoms) {
            phantomTicks = 0;
        }

        for (ServerPlayerEntity player : server.getPlayerManager().getPlayerList()) {
            PlayerProfile profile = store.peek(player.getUuid());
            if (doEffects) {
                applyNightVision(player, profile);
            }
            if (doPhantoms && !profile.phantomSpawning) {
                player.getStatHandler().setStat(player,
                        Stats.CUSTOM.getOrCreateStat(Stats.TIME_SINCE_REST), 0);
            }
        }
    }

    /** Called the moment a setting is toggled, so the menu feels immediate. */
    public void applyNow(ServerPlayerEntity player) {
        PlayerProfile profile = store.peek(player.getUuid());
        applyNightVision(player, profile);
        if (!profile.phantomSpawning) {
            player.getStatHandler().setStat(player,
                    Stats.CUSTOM.getOrCreateStat(Stats.TIME_SINCE_REST), 0);
        }
    }

    /**
     * Re-applied on a timer rather than once, so it survives death, dimension changes and milk.
     * Ambient with no particles or icon so it does not clutter the HUD.
     */
    private static void applyNightVision(ServerPlayerEntity player, PlayerProfile profile) {
        StatusEffectInstance active = player.getStatusEffect(StatusEffects.NIGHT_VISION);
        if (profile.nightVision) {
            if (active == null) {
                player.addStatusEffect(new StatusEffectInstance(StatusEffects.NIGHT_VISION,
                        StatusEffectInstance.INFINITE, 0, true, false, false));
            }
        } else if (active != null && active.isInfinite() && active.isAmbient()) {
            // Only clear the infinite ambient one this mod applied; potions and beacons are left be.
            player.removeStatusEffect(StatusEffects.NIGHT_VISION);
        }
    }

}
