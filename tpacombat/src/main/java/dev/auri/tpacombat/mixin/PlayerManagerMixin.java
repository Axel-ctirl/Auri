package dev.auri.tpacombat.mixin;

import dev.auri.tpacombat.DisconnectHandler;
import net.minecraft.server.PlayerManager;
import net.minecraft.server.network.ServerPlayerEntity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * Head of {@code remove} is the last moment a leaving player is still in the world: vanilla's very
 * next steps are {@code savePlayerData} and removal. Combat-log punishment has to happen here so
 * the death is real and gets saved.
 */
@Mixin(PlayerManager.class)
public class PlayerManagerMixin {

    @Inject(method = "remove", at = @At("HEAD"))
    private void tpacombat$onRemove(ServerPlayerEntity player, CallbackInfo ci) {
        DisconnectHandler.onRemove(player);
    }
}
