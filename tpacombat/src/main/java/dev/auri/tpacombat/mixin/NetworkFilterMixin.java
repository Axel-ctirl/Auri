package dev.auri.tpacombat.mixin;

import dev.auri.tpacombat.PacketFilter;
import io.netty.channel.ChannelFutureListener;
import net.minecraft.network.packet.Packet;
import net.minecraft.server.network.ServerCommonNetworkHandler;
import net.minecraft.server.network.ServerPlayNetworkHandler;
import net.minecraft.server.network.ServerPlayerEntity;
import org.jetbrains.annotations.Nullable;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * Per-player filtering of outgoing packets.
 *
 * <p>Targets {@code send} rather than {@code sendPacket} because the latter simply delegates here,
 * so this catches every send path.
 */
@Mixin(ServerCommonNetworkHandler.class)
public class NetworkFilterMixin {

    @Inject(method = "send", at = @At("HEAD"), cancellable = true)
    private void tpacombat$filterOutgoing(Packet<?> packet, @Nullable ChannelFutureListener listener,
                                          CallbackInfo ci) {
        if (!((Object) this instanceof ServerPlayNetworkHandler handler)) {
            return;
        }
        ServerPlayerEntity player = handler.player;
        if (player == null) {
            return;
        }
        if (PacketFilter.shouldDrop(player, packet)) {
            ci.cancel();
        }
    }
}
