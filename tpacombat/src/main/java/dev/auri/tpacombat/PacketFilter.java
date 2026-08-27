package dev.auri.tpacombat;

import net.minecraft.entity.EntityStatuses;
import net.minecraft.network.packet.Packet;
import net.minecraft.network.packet.s2c.play.ChatMessageS2CPacket;
import net.minecraft.network.packet.s2c.play.EntityStatusS2CPacket;
import net.minecraft.network.packet.s2c.play.ExplosionS2CPacket;
import net.minecraft.network.packet.s2c.play.GameMessageS2CPacket;
import net.minecraft.server.network.ServerPlayerEntity;
import net.minecraft.text.Text;
import net.minecraft.text.TranslatableTextContent;

/**
 * Decides whether an outgoing packet should be withheld from a player based on their settings.
 * Called from the network mixin, which is why the store is handed over statically at startup.
 *
 * <p>This runs for every packet sent to every player, so it is written to bail out on the very
 * first check for the overwhelming majority of traffic (movement, chunks, entity updates) without
 * touching the profile store at all.
 */
public final class PacketFilter {

    private static volatile PlayerDataStore store;

    private PacketFilter() {
    }

    public static void init(PlayerDataStore dataStore) {
        store = dataStore;
    }

    public static boolean shouldDrop(ServerPlayerEntity player, Packet<?> packet) {
        // Type first: anything we never filter leaves without a map lookup.
        if (packet instanceof EntityStatusS2CPacket status) {
            if (status.getStatus() != EntityStatuses.USE_TOTEM_OF_UNDYING) {
                return false;
            }
            return !profile(player).totemParticles;
        }
        if (packet instanceof ExplosionS2CPacket explosion) {
            // Dropping a packet that carries knockback would rob the player of the physics, so
            // only the purely decorative ones are withheld.
            if (explosion.playerKnockback().isPresent()) {
                return false;
            }
            return !profile(player).explosionParticles;
        }
        if (packet instanceof ChatMessageS2CPacket) {
            return !profile(player).publicChat;
        }
        if (packet instanceof GameMessageS2CPacket message) {
            String key = translationKey(message.content());
            if (key == null) {
                return false;
            }
            return shouldDropSystemMessage(profile(player), key);
        }
        return false;
    }

    private static PlayerProfile profile(ServerPlayerEntity player) {
        PlayerDataStore dataStore = store;
        return dataStore == null ? new PlayerProfile() : dataStore.peek(player.getUuid());
    }

    /**
     * Vanilla system messages are translatable, and their keys are stable across versions, so the
     * key is a far more reliable classifier than trying to match rendered text.
     */
    private static boolean shouldDropSystemMessage(PlayerProfile profile, String key) {
        if (key.startsWith("death.")) {
            return !profile.deathMessages;
        }
        if (key.startsWith("chat.type.advancement.")) {
            return !profile.advancementMessages;
        }
        if (key.startsWith("multiplayer.player.")) {
            return !profile.joinLeaveMessages;
        }
        return false;
    }

    private static String translationKey(Text content) {
        if (content.getContent() instanceof TranslatableTextContent translatable) {
            return translatable.getKey();
        }
        return null;
    }
}
