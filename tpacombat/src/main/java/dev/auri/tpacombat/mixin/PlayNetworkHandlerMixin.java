package dev.auri.tpacombat.mixin;

import dev.auri.tpacombat.DisconnectHandler;
import net.minecraft.network.DisconnectionInfo;
import net.minecraft.server.network.ServerPlayNetworkHandler;
import net.minecraft.server.network.ServerPlayerEntity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * Leave handling, hooked at the head of {@code onDisconnected}.
 *
 * <p>This is the earliest point at which a leaving player is still fully in the world, before
 * vanilla removes and saves them. It is deliberately earlier than {@code PlayerManager.remove},
 * which this used to hook: a dedicated combat-logging mod hooks here, so hooking later meant
 * losing every race and never punishing anyone.
 */
@Mixin(ServerPlayNetworkHandler.class)
public class PlayNetworkHandlerMixin {

    @Shadow
    public ServerPlayerEntity player;

    @Inject(method = "onDisconnected", at = @At("HEAD"))
    private void tpacombat$onDisconnected(DisconnectionInfo info, CallbackInfo ci) {
        if (this.player != null) {
            DisconnectHandler.onRemove(this.player);
        }
    }
}
