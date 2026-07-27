package dev.auri.combat.config;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.minimessage.MiniMessage;
import net.kyori.adventure.text.minimessage.tag.resolver.Placeholder;
import net.kyori.adventure.text.minimessage.tag.resolver.TagResolver;
import org.bukkit.command.CommandSender;
import org.bukkit.configuration.file.FileConfiguration;

import java.util.HashMap;
import java.util.Map;

/**
 * MiniMessage-backed message lookup.
 *
 * <p>Placeholder values are inserted with {@link Placeholder#unparsed}, so a player named
 * {@code <red>Steve} renders as literal text instead of smuggling formatting into a broadcast.
 */
public final class Messages {

    private final MiniMessage mm = MiniMessage.miniMessage();
    private final Map<String, String> raw = new HashMap<>();
    private Component prefix = Component.empty();

    public void load(FileConfiguration cfg) {
        raw.clear();
        var section = cfg.getConfigurationSection("messages");
        if (section != null) {
            for (String key : section.getKeys(true)) {
                if (section.isString(key)) {
                    raw.put(key, section.getString(key, ""));
                }
            }
        }
        prefix = mm.deserialize(raw.getOrDefault("prefix", ""));
    }

    /** True when the message is configured as an empty string, i.e. deliberately disabled. */
    public boolean isDisabled(String path) {
        return raw.getOrDefault(path, "").isEmpty();
    }

    /** Renders {@code path}, substituting alternating key/value pairs as {@code <key>} tags. */
    public Component get(String path, Object... placeholders) {
        String template = raw.get(path);
        if (template == null || template.isEmpty()) {
            return Component.empty();
        }
        return mm.deserialize(template, resolvers(placeholders));
    }

    /** Renders {@code path} with the configured prefix in front. */
    public Component prefixed(String path, Object... placeholders) {
        if (isDisabled(path)) {
            return Component.empty();
        }
        return prefix.append(get(path, placeholders));
    }

    public void send(CommandSender to, String path, Object... placeholders) {
        if (isDisabled(path)) {
            return;
        }
        to.sendMessage(prefixed(path, placeholders));
    }

    /** Sends without the prefix — for action bars and other tight spaces. */
    public void sendBare(CommandSender to, String path, Object... placeholders) {
        if (isDisabled(path)) {
            return;
        }
        to.sendMessage(get(path, placeholders));
    }

    private TagResolver resolvers(Object... placeholders) {
        if (placeholders.length == 0) {
            return TagResolver.empty();
        }
        if (placeholders.length % 2 != 0) {
            throw new IllegalArgumentException("placeholders must be key/value pairs");
        }
        TagResolver.Builder builder = TagResolver.builder();
        for (int i = 0; i < placeholders.length; i += 2) {
            builder.resolver(Placeholder.unparsed(
                    String.valueOf(placeholders[i]),
                    String.valueOf(placeholders[i + 1])));
        }
        return builder.build();
    }
}
