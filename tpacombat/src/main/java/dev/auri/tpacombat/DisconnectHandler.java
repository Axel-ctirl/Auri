package dev.auri.tpacombat;

import net.minecraft.server.network.ServerPlayerEntity;

/**
 * Runs the mod's leave handling from vanilla's own removal path.
 *
 * <p>Fabric's {@code ServerPlayConnectionEvents.DISCONNECT} is not usable for this. It is fired
 * from whichever of {@code Connection.channelInactive} or {@code handleDisconnection} happens
 * first, and the former runs on a netty IO thread. That makes it both off-thread for anything
 * touching the world and unordered with respect to the player actually leaving it -- so a
 * combat-log kill issued there could land on the wrong thread, or after the player was already
 * removed and saved, and quietly do nothing.
 *
 * <p>{@code PlayerManager.remove} is always on the server thread and its first actions happen
 * while the player is still in the world, before {@code savePlayerData}. Killing there produces a
 * normal death -- items drop, the death is saved -- which is exactly what combat logging needs.
 */
public final class DisconnectHandler {

    private static volatile CombatManager combat;
    private static volatile TpaManager tpa;
    private static volatile PlaytimeTracker playtime;

    private DisconnectHandler() {
    }

    public static void init(CombatManager combatManager, TpaManager tpaManager, PlaytimeTracker tracker) {
        combat = combatManager;
        tpa = tpaManager;
        playtime = tracker;
    }

    /** Called from the mixin at the head of PlayerManager.remove. */
    public static void onRemove(ServerPlayerEntity player) {
        CombatManager combatManager = combat;
        if (combatManager != null) {
            combatManager.onDisconnect(player);
        }
        TpaManager tpaManager = tpa;
        if (tpaManager != null) {
            tpaManager.onDisconnect(player);
        }
        PlaytimeTracker tracker = playtime;
        if (tracker != null) {
            tracker.onDisconnect(player);
        }
    }
}
