package dev.auri.tpacombat.mixin;

import com.llamalad7.mixinextras.injector.ModifyExpressionValue;
import dev.auri.tpacombat.PearlSettings;
import net.minecraft.entity.Entity;
import net.minecraft.entity.projectile.thrown.EnderPearlEntity;
import net.minecraft.server.network.ServerPlayerEntity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;

/**
 * Makes "Ender Pearls Vanish On Death" a per-player choice.
 *
 * <p>Vanilla already discards a pearl when its owner dies, gated on the
 * {@code ender_pearls_vanish_on_death} game rule. Rather than duplicating that, this substitutes
 * the owner's own preference for the rule's value at the point it is read, so vanilla still does
 * the discarding and there is only one implementation of the behaviour.
 *
 * <p>If the owner cannot be resolved to a player the game rule's real value is returned, so the
 * worst case is plain vanilla behaviour.
 */
@Mixin(EnderPearlEntity.class)
public class EnderPearlMixin {

    @ModifyExpressionValue(
            method = "tick",
            at = @At(value = "INVOKE",
                    target = "Lnet/minecraft/world/rule/GameRules;getValue(Lnet/minecraft/world/rule/GameRule;)Ljava/lang/Object;"))
    private Object tpacombat$perPlayerPearlVanish(Object original) {
        Entity owner = ((EnderPearlEntity) (Object) this).getOwner();
        if (owner instanceof ServerPlayerEntity player) {
            Boolean preference = PearlSettings.vanishOnDeath(player);
            if (preference != null) {
                return preference;
            }
        }
        return original;
    }
}
