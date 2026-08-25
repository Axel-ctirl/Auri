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
 */
public final class PacketFilter {

    private static volatile PlayerDataStore store;

    private PacketFilter() {
    }

    public static void init(PlayerDataStore dataStore) {
        store = dataStore;
    }

    public static boolean shouldDrop(ServerPlayerEntity player, Packet<?> packet) {
        PlayerDataStore dataStore = store;
        if (dataStore == null) {
            return false;
        }
        PlayerProfile profile = dataStore.get(player.getUuid());

        if (packet instanceof EntityStatusS2CPacket status) {
            return !profile.totemParticles && status.getStatus() == EntityStatuses.USE_TOTEM_OF_UNDYING;
        }
        if (packet instanceof ExplosionS2CPacket explosion) {
            // Dropping a packet that carries knockback would rob the player of the physics, so
            // only the purely decorative ones are withheld.
            return !profile.explosionParticles && explosion.playerKnockback().isEmpty();
        }
        if (packet instanceof ChatMessageS2CPacket) {
            return !profile.publicChat;
        }
        if (packet instanceof GameMessageS2CPacket message) {
            return shouldDropSystemMessage(profile, message.content());
        }
        return false;
    }

    /**
     * Vanilla system messages are translatable, and their keys are stable across versions, so the
     * key is a far more reliable classifier than trying to match rendered text.
     */
    private static boolean shouldDropSystemMessage(PlayerProfile profile, Text content) {
        String key = translationKey(content);
        if (key == null) {
            return false;
        }
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
