package dev.auri.tpacombat;

import net.minecraft.registry.RegistryKey;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.network.ServerPlayerEntity;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.text.Text;
import net.minecraft.util.math.BlockPos;
import net.minecraft.world.World;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/** Pending teleport requests, the post-accept warmup, and the self-inflicted-cancel cooldown. */
public final class TpaManager {

    private final CombatManager combat;
    private final BlockListStore blocks = new BlockListStore();

    /** Keyed by the request's target; newest request is at the tail. */
    private final Map<UUID, Deque<Request>> pending = new HashMap<>();
    private final Map<UUID, Warmup> warmups = new HashMap<>();
    private final Map<UUID, Long> cooldowns = new HashMap<>();
    private int tickCounter;

    public TpaManager(CombatManager combat) {
        this.combat = combat;
    }

    public BlockListStore blocks() {
        return blocks;
    }

    public int timeoutSeconds() {
        return Config.get().tpa.requestTimeoutSeconds;
    }

    private long timeoutMillis() {
        return timeoutSeconds() * 1000L;
    }

    /** Drops expired requests and requests from players who have since gone offline. */
    private Deque<Request> prune(MinecraftServer server, UUID target) {
        Deque<Request> queue = pending.get(target);
        if (queue == null) {
            return null;
        }
        queue.removeIf(r -> r.expired() || server.getPlayerManager().getPlayer(r.requester()) == null);
        if (queue.isEmpty()) {
            pending.remove(target);
            return null;
        }
        return queue;
    }

    public boolean hasPendingFrom(ServerPlayerEntity requester, ServerPlayerEntity target) {
        Deque<Request> queue = prune(requester.getEntityWorld().getServer(), target.getUuid());
        return queue != null && queue.stream().anyMatch(r -> r.requester().equals(requester.getUuid()));
    }

    public void addRequest(ServerPlayerEntity requester, ServerPlayerEntity target) {
        pending.computeIfAbsent(target.getUuid(), k -> new ArrayDeque<>())
                .addLast(new Request(requester.getUuid(), requester.getGameProfile().name(),
                        System.currentTimeMillis() + timeoutMillis()));
    }

    public Request peekLatest(ServerPlayerEntity target) {
        Deque<Request> queue = prune(target.getEntityWorld().getServer(), target.getUuid());
        return queue == null ? null : queue.peekLast();
    }

    public Request pollLatest(ServerPlayerEntity target) {
        Deque<Request> queue = prune(target.getEntityWorld().getServer(), target.getUuid());
        if (queue == null) {
            return null;
        }
        Request request = queue.pollLast();
        if (queue.isEmpty()) {
            pending.remove(target.getUuid());
        }
        return request;
    }

    public void dropRequestsFrom(UUID owner, UUID requester) {
        Deque<Request> queue = pending.get(owner);
        if (queue != null) {
            queue.removeIf(r -> r.requester().equals(requester));
        }
    }

    public void startWarmup(ServerPlayerEntity requester, ServerPlayerEntity target) {
        cancelWarmup(requester.getUuid());
        int delay = Config.get().tpa.teleportDelaySeconds;
        if (delay == 0) {
            completeTeleport(requester, target);
            return;
        }
        Warmup warmup = new Warmup(requester, target, delay);
        warmup.showCountdown(requester);
        warmups.put(requester.getUuid(), warmup);
    }

    public void onEndTick(MinecraftServer server) {
        if (++tickCounter < 20) {
            return;
        }
        tickCounter = 0;
        if (warmups.isEmpty()) {
            return;
        }
        for (Warmup warmup : new ArrayList<>(warmups.values())) {
            warmup.tick(server);
        }
    }

    private void completeTeleport(ServerPlayerEntity requester, ServerPlayerEntity target) {
        ServerWorld world = target.getEntityWorld();
        requester.teleport(world, target.getX(), target.getY(), target.getZ(), Set.of(),
                target.getYaw(), target.getPitch(), true);
        Messages.actionBar(requester, Messages.tpaTeleported(target.getGameProfile().name()));
    }

    public void cancelWarmup(UUID requesterId) {
        warmups.remove(requesterId);
    }

    private void applyCancelCooldown(UUID requesterId) {
        int seconds = Config.get().tpa.cancelCooldownSeconds;
        if (seconds > 0) {
            cooldowns.put(requesterId, System.currentTimeMillis() + seconds * 1000L);
        }
    }

    public int cooldownRemaining(ServerPlayerEntity player) {
        Long until = cooldowns.get(player.getUuid());
        if (until == null) {
            return 0;
        }
        long remaining = until - System.currentTimeMillis();
        if (remaining <= 0L) {
            cooldowns.remove(player.getUuid());
            return 0;
        }
        return (int) Math.ceil(remaining / 1000.0);
    }

    public void onDisconnect(ServerPlayerEntity player) {
        pending.remove(player.getUuid());
        cancelWarmup(player.getUuid());
    }

    public void onServerStopping() {
        pending.clear();
        warmups.clear();
        cooldowns.clear();
    }

    public record Request(UUID requester, String requesterName, long expiresAt) {
        public boolean expired() {
            return expiresAt <= System.currentTimeMillis();
        }
    }

    private final class Warmup {

        private final UUID requesterId;
        private final UUID targetId;
        private final String targetName;
        private final RegistryKey<World> startDimension;
        private final BlockPos startPos;
        private final boolean cancelOnMove;
        private int secondsLeft;

        Warmup(ServerPlayerEntity requester, ServerPlayerEntity target, int seconds) {
            this.requesterId = requester.getUuid();
            this.targetId = target.getUuid();
            this.targetName = target.getGameProfile().name();
            this.startDimension = requester.getEntityWorld().getRegistryKey();
            this.startPos = requester.getBlockPos();
            this.cancelOnMove = Config.get().tpa.cancelOnMove;
            this.secondsLeft = seconds;
        }

        void tick(MinecraftServer server) {
            ServerPlayerEntity requester = server.getPlayerManager().getPlayer(requesterId);
            if (requester == null || requester.isDead()) {
                cancelWarmup(requesterId);
                return;
            }
            ServerPlayerEntity target = server.getPlayerManager().getPlayer(targetId);
            if (target == null) {
                abort(requester, Messages.tpaCancelledOffline(targetName), false);
                return;
            }
            if (cancelOnMove && movedFrom(requester)) {
                abort(requester, Messages.tpaCancelledMoved(), true);
                return;
            }
            if (combat.isTagged(requester)) {
                abort(requester, Messages.tpaCancelledCombat(), true);
                return;
            }

            if (--secondsLeft <= 0) {
                cancelWarmup(requesterId);
                completeTeleport(requester, target);
            } else {
                showCountdown(requester);
            }
        }

        void showCountdown(ServerPlayerEntity requester) {
            Messages.actionBar(requester, Messages.tpaWarmup(secondsLeft));
        }

        private boolean movedFrom(ServerPlayerEntity requester) {
            return !requester.getEntityWorld().getRegistryKey().equals(startDimension)
                    || !requester.getBlockPos().equals(startPos);
        }

        /** Moving or getting hit is the player's own doing, so those two apply the cooldown. */
        private void abort(ServerPlayerEntity requester, Text message, boolean selfInflicted) {
            Messages.actionBar(requester, message);
            cancelWarmup(requesterId);
            if (selfInflicted) {
                applyCancelCooldown(requesterId);
            }
        }
    }
}
