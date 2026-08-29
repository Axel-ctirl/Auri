package dev.auri.tpacombat;

import net.minecraft.server.network.ServerPlayerEntity;

/** Static bridge so the phantom targeting mixin can read a player's preference. */
public final class PhantomTargeting {

    private static volatile PlayerDataStore store;

    private PhantomTargeting() {
    }

    public static void init(PlayerDataStore dataStore) {
        store = dataStore;
    }

    /**
     * Sort key: players who left phantom spawning on come first, everyone else after. Anything
     * that is not a resolvable player sorts as "on", so unknown cases keep vanilla ordering.
     */
    public static int priority(Object candidate) {
        PlayerDataStore dataStore = store;
        if (dataStore == null || !(candidate instanceof ServerPlayerEntity player)) {
            return 0;
        }
        return dataStore.peek(player.getUuid()).phantomSpawning ? 0 : 1;
    }
}
