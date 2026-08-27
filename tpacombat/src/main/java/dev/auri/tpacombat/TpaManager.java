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

    public void addRequest(ServerPlayerEntity requester, ServerPlayerEntity target, boolean here) {
        pending.computeIfAbsent(target.getUuid(), k -> new ArrayDeque<>())
                .addLast(new Request(requester.getUuid(), requester.getGameProfile().name(),
                        System.currentTimeMillis() + timeoutMillis(), here));
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

    /** {@code mover} is whoever is being teleported; for /tpahere that is the accepting player. */
    public void startWarmup(ServerPlayerEntity mover, ServerPlayerEntity destination) {
        cancelWarmup(mover.getUuid());
        int delay = Config.get().tpa.teleportDelaySeconds;
        if (delay == 0) {
            completeTeleport(mover, destination);
            return;
        }
        Warmup warmup = new Warmup(mover, destination, delay);
        warmup.showCountdown(mover);
        warmups.put(mover.getUuid(), warmup);
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

    private void completeTeleport(ServerPlayerEntity mover, ServerPlayerEntity destination) {
        ServerWorld world = destination.getEntityWorld();
        mover.teleport(world, destination.getX(), destination.getY(), destination.getZ(), Set.of(),
                destination.getYaw(), destination.getPitch(), true);
        Messages.actionBar(mover, Messages.tpaTeleported(destination.getGameProfile().name()));
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

    /**
     * {@code here} distinguishes /tpahere from /tpa: it decides which of the two players moves
     * when the request is accepted.
     */
    public record Request(UUID requester, String requesterName, long expiresAt, boolean here) {
        public boolean expired() {
            return expiresAt <= System.currentTimeMillis();
        }
    }

    private final class Warmup {

        private final UUID moverId;
        private final UUID destinationId;
        private final String destinationName;
        private final RegistryKey<World> startDimension;
        private final BlockPos startPos;
        private final boolean cancelOnMove;
        private int secondsLeft;

        Warmup(ServerPlayerEntity mover, ServerPlayerEntity destination, int seconds) {
            this.moverId = mover.getUuid();
            this.destinationId = destination.getUuid();
            this.destinationName = destination.getGameProfile().name();
            this.startDimension = mover.getEntityWorld().getRegistryKey();
            this.startPos = mover.getBlockPos();
            this.cancelOnMove = Config.get().tpa.cancelOnMove;
            this.secondsLeft = seconds;
        }

        void tick(MinecraftServer server) {
            ServerPlayerEntity mover = server.getPlayerManager().getPlayer(moverId);
            if (mover == null || mover.isDead()) {
                cancelWarmup(moverId);
                return;
            }
            ServerPlayerEntity destination = server.getPlayerManager().getPlayer(destinationId);
            if (destination == null) {
                abort(mover, Messages.tpaCancelledOffline(destinationName), false);
                return;
            }
            if (cancelOnMove && movedFrom(mover)) {
                abort(mover, Messages.tpaCancelledMoved(), true);
                return;
            }
            if (combat.isTagged(mover)) {
                abort(mover, Messages.tpaCancelledCombat(), true);
                return;
            }

            if (--secondsLeft <= 0) {
                cancelWarmup(moverId);
                completeTeleport(mover, destination);
            } else {
                showCountdown(mover);
            }
        }

        void showCountdown(ServerPlayerEntity mover) {
            Messages.actionBar(mover, Messages.tpaWarmup(secondsLeft));
        }

        private boolean movedFrom(ServerPlayerEntity mover) {
            return !mover.getEntityWorld().getRegistryKey().equals(startDimension)
                    || !mover.getBlockPos().equals(startPos);
        }

        /** Moving or getting hit is the player's own doing, so those two apply the cooldown. */
        private void abort(ServerPlayerEntity mover, Text message, boolean selfInflicted) {
            Messages.actionBar(mover, message);
            cancelWarmup(moverId);
            if (selfInflicted) {
                applyCancelCooldown(moverId);
            }
        }
    }
}
