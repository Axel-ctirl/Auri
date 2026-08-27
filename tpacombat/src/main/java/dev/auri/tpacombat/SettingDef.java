package dev.auri.tpacombat;

import net.minecraft.text.Text;
import net.minecraft.util.Formatting;

import java.util.List;
import java.util.Locale;
import java.util.function.BiConsumer;
import java.util.function.Function;
import java.util.function.Predicate;

/**
 * One setting. Each one gets its own screen listing every value it can take, so the options are
 * visible up front rather than discovered by clicking through them.
 */
public sealed interface SettingDef permits SettingDef.Toggle, SettingDef.Choice {

    String id();

    String category();

    String label();

    /** One line explaining what the setting does, shown on the setting's own screen. */
    String description();

    /** Stable keys for every value this setting can take, in display order. */
    List<String> optionKeys();

    String currentKey(PlayerProfile profile);

    /** Returns false for an unrecognised key rather than throwing. */
    boolean apply(PlayerProfile profile, String key);

    Text optionLabel(String key);

    default Text valueText(PlayerProfile profile) {
        return optionLabel(currentKey(profile));
    }

    record Toggle(String id, String category, String label, String description,
                  Predicate<PlayerProfile> getter,
                  BiConsumer<PlayerProfile, Boolean> setter) implements SettingDef {

        @Override
        public List<String> optionKeys() {
            return List.of("on", "off");
        }

        @Override
        public String currentKey(PlayerProfile profile) {
            return getter.test(profile) ? "on" : "off";
        }

        @Override
        public boolean apply(PlayerProfile profile, String key) {
            if (key.equals("on")) {
                setter.accept(profile, true);
                return true;
            }
            if (key.equals("off")) {
                setter.accept(profile, false);
                return true;
            }
            return false;
        }

        @Override
        public Text optionLabel(String key) {
            boolean on = key.equals("on");
            return Text.literal(on ? "ON" : "OFF").formatted(on ? Formatting.GREEN : Formatting.RED);
        }
    }

    record Choice(String id, String category, String label, String description,
                  Function<PlayerProfile, Visibility> getter,
                  BiConsumer<PlayerProfile, Visibility> setter) implements SettingDef {

        @Override
        public List<String> optionKeys() {
            return java.util.Arrays.stream(Visibility.values())
                    .map(v -> v.name().toLowerCase(Locale.ROOT))
                    .toList();
        }

        @Override
        public String currentKey(PlayerProfile profile) {
            return getter.apply(profile).name().toLowerCase(Locale.ROOT);
        }

        @Override
        public boolean apply(PlayerProfile profile, String key) {
            for (Visibility value : Visibility.values()) {
                if (value.name().equalsIgnoreCase(key)) {
                    setter.accept(profile, value);
                    return true;
                }
            }
            return false;
        }

        @Override
        public Text optionLabel(String key) {
            for (Visibility value : Visibility.values()) {
                if (value.name().equalsIgnoreCase(key)) {
                    return Text.literal(value.label()).formatted(value.color());
                }
            }
            return Text.literal(key);
        }
    }
}
