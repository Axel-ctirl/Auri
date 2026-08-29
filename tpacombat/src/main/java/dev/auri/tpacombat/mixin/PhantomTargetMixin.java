package dev.auri.tpacombat.mixin;

import dev.auri.tpacombat.PhantomTargeting;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

import java.util.Comparator;
import java.util.List;

/**
 * Makes phantoms prefer players who left phantom spawning on.
 *
 * <p>Vanilla picks the highest player within range, which meant a player who had switched phantom
 * spawning off could still be chosen ahead of the player the phantoms actually spawned for, just
 * by standing slightly higher. This reorders the same candidate list rather than removing anyone
 * from it, so a player who opted out is still targeted when nobody who opted in is in range --
 * switching the setting off gets you deprioritised, never invulnerable.
 *
 * <p>Vanilla's own ordering is kept as the tie-break within each group.
 */
@Mixin(targets = "net.minecraft.entity.mob.PhantomEntity$FindTargetGoal")
public class PhantomTargetMixin {

    @SuppressWarnings({"unchecked", "rawtypes"})
    @Redirect(
            method = "canStart",
            at = @At(value = "INVOKE", target = "Ljava/util/List;sort(Ljava/util/Comparator;)V"))
    private void tpacombat$preferOptedIn(List list, Comparator vanillaOrder) {
        Comparator<Object> byOptIn = Comparator.comparingInt(PhantomTargeting::priority);
        list.sort(byOptIn.thenComparing(vanillaOrder));
    }
}
