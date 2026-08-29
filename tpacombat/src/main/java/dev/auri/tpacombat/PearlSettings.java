package dev.auri.tpacombat;

import net.minecraft.server.network.ServerPlayerEntity;

/** Static bridge so the ender pearl mixin can read a player's preference. */
public final class PearlSettings {

    private static volatile PlayerDataStore store;

    private PearlSettings() {
    }

    public static void init(PlayerDataStore dataStore) {
        store = dataStore;
    }

    /** Null means "no opinion", leaving the game rule's own value in force. */
    public static Boolean vanishOnDeath(ServerPlayerEntity player) {
        PlayerDataStore dataStore = store;
        return dataStore == null ? null : dataStore.peek(player.getUuid()).enderPearlsVanishOnDeath;
    }
}
