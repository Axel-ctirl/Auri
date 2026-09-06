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
 * <p>The hook is the head of {@code ServerPlayNetworkHandler.onDisconnected}, the same seam a
 * dedicated combat-logging mod uses. It is the earliest point at which the player is still fully
 * in the world, before vanilla removes and saves them, so the kill produces a normal death: items
 * drop and the dead state is what gets written. Hooking later, at {@code PlayerManager.remove},
 * meant another mod on this seam always got there first and this one never fired.
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
