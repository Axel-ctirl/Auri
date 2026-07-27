package dev.auri.combat.tpa;

import java.util.UUID;

/**
 * A pending teleport request.
 *
 * @param sender  who ran the command
 * @param target  who has to accept
 * @param type    which direction the traveller moves
 * @param expiresAt epoch millis after which the request is dead
 */
public record TpaRequest(UUID sender, UUID target, Type type, long expiresAt) {

    public enum Type {
        /** {@code /tpa} — the sender travels to the target. */
        TO_TARGET,
        /** {@code /tpahere} — the target travels to the sender. */
        TO_SENDER
    }

    public boolean isExpired() {
        return System.currentTimeMillis() >= expiresAt;
    }

    /** The player who actually gets moved. */
    public UUID traveller() {
        return type == Type.TO_TARGET ? sender : target;
    }

    /** The player who stays put and provides the destination. */
    public UUID destination() {
        return type == Type.TO_TARGET ? target : sender;
    }
}
