package dev.auri.tpacombat;

import net.minecraft.text.Text;
import net.minecraft.util.Formatting;

import java.util.function.BiConsumer;
import java.util.function.Function;
import java.util.function.Predicate;

/**
 * One row in the settings menu. Clicking a row cycles it, which covers both on/off toggles and the
 * four-way visibility settings without needing separate UI for each.
 */
public sealed interface SettingDef permits SettingDef.Toggle, SettingDef.Choice {

    String id();

    String category();

    String label();

    Text valueText(PlayerProfile profile);

    void cycle(PlayerProfile profile);

    record Toggle(String id, String category, String label,
                  Predicate<PlayerProfile> getter,
                  BiConsumer<PlayerProfile, Boolean> setter) implements SettingDef {

        @Override
        public Text valueText(PlayerProfile profile) {
            boolean on = getter.test(profile);
            return Text.literal(on ? "ON" : "OFF").formatted(on ? Formatting.GREEN : Formatting.RED);
        }

        @Override
        public void cycle(PlayerProfile profile) {
            setter.accept(profile, !getter.test(profile));
        }
    }

    record Choice(String id, String category, String label,
                  Function<PlayerProfile, Visibility> getter,
                  BiConsumer<PlayerProfile, Visibility> setter) implements SettingDef {

        @Override
        public Text valueText(PlayerProfile profile) {
            Visibility value = getter.apply(profile);
            return Text.literal(value.label()).formatted(value.color());
        }

        @Override
        public void cycle(PlayerProfile profile) {
            setter.accept(profile, getter.apply(profile).next());
        }
    }
}
