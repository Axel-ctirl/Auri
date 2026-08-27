package dev.auri.tpacombat;

import net.minecraft.server.MinecraftServer;
import net.minecraft.server.network.ServerPlayerEntity;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Follows are one-directional. When two players follow each other they count as friends, which is
 * what the "Friends" visibility level checks.
 */
public final class SocialManager {

    private final PlayerDataStore store;

    public SocialManager(PlayerDataStore store) {
        this.store = store;
    }

    public boolean follow(UUID owner, UUID target, String targetName) {
        if (owner.equals(target)) {
            return false;
        }
        PlayerProfile profile = store.get(owner);
        if (!profile.following.add(target.toString())) {
            return false;
        }
        store.get(target).lastKnownName = targetName;
        store.markDirty();
        return true;
    }

    public boolean unfollow(UUID owner, UUID target) {
        PlayerProfile profile = store.get(owner);
        if (!profile.following.remove(target.toString())) {
            return false;
        }
        store.markDirty();
        return true;
    }

    /** True when {@code owner} follows {@code other}. */
    public boolean isFollowing(UUID owner, UUID other) {
        return store.peek(owner).following.contains(other.toString());
    }

    public boolean areFriends(UUID a, UUID b) {
        return isFollowing(a, b) && isFollowing(b, a);
    }

    public List<UUID> following(UUID owner) {
        List<UUID> out = new ArrayList<>();
        for (String id : store.peek(owner).following) {
            try {
                out.add(UUID.fromString(id));
            } catch (IllegalArgumentException ignored) {
                // ignore corrupt entries
            }
        }
        return out;
    }

    /** Reverse lookup, so it walks every known profile rather than a maintained index. */
    public List<UUID> followers(UUID owner) {
        String target = owner.toString();
        List<UUID> out = new ArrayList<>();
        for (Map.Entry<UUID, PlayerProfile> entry : store.all().entrySet()) {
            if (entry.getValue().following.contains(target)) {
                out.add(entry.getKey());
            }
        }
        return out;
    }

    public List<UUID> friends(UUID owner) {
        List<UUID> out = new ArrayList<>();
        for (UUID candidate : following(owner)) {
            if (isFollowing(candidate, owner)) {
                out.add(candidate);
            }
        }
        return out;
    }

    /** Prefers the live player name and falls back to whatever was last recorded. */
    public String nameOf(MinecraftServer server, UUID uuid) {
        ServerPlayerEntity online = server.getPlayerManager().getPlayer(uuid);
        if (online != null) {
            return online.getGameProfile().name();
        }
        String stored = store.peek(uuid).lastKnownName;
        return stored.isEmpty() ? uuid.toString().substring(0, 8) : stored;
    }
}
