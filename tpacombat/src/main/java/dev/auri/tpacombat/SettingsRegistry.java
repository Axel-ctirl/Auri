package dev.auri.tpacombat;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * The single source of truth for what appears in the settings menu. The dialogs and the /settings
 * command both read this, so adding a setting here adds it to both.
 */
public final class SettingsRegistry {

    /** {@code sprite} is an atlas texture path, rendered inline via the object text component. */
    public record Category(String id, String title, String sprite) {
    }

    private static final List<Category> CATEGORIES = List.of(
            new Category("chat", "Chat", "item/oak_sign"),
            new Category("notifications", "Notifications", "item/bell"),
            new Category("pvp", "PvP", "item/diamond_sword"),
            new Category("privacy", "Privacy", "item/barrier"),
            new Category("general", "General", "item/comparator"),
            new Category("friends", "Friends", "item/name_tag"));

    private static final List<SettingDef> SETTINGS = List.of(
            new SettingDef.Toggle("chat.public", "chat", "Public Chat",
                    "Show messages other players send in public chat.",
                    p -> p.publicChat, (p, v) -> p.publicChat = v),
            new SettingDef.Choice("chat.private", "chat", "Private Messages",
                    "Who is allowed to send you private messages.",
                    p -> p.privateMessages, (p, v) -> p.privateMessages = v),
            new SettingDef.Toggle("chat.server", "chat", "Server Messages",
                    "Announcements from the server, such as combat logs.",
                    p -> p.serverMessages, (p, v) -> p.serverMessages = v),
            new SettingDef.Toggle("chat.death", "chat", "Death Messages",
                    "Show a message when a player dies.",
                    p -> p.deathMessages, (p, v) -> p.deathMessages = v),
            new SettingDef.Toggle("chat.advancement", "chat", "Advancement Messages",
                    "Show a message when a player earns an advancement.",
                    p -> p.advancementMessages, (p, v) -> p.advancementMessages = v),
            new SettingDef.Toggle("chat.joinleave", "chat", "Join/Leave Messages",
                    "Show a message when a player joins or leaves.",
                    p -> p.joinLeaveMessages, (p, v) -> p.joinLeaveMessages = v),

            new SettingDef.Toggle("notifications.tpa", "notifications", "TPA Alerts",
                    "Be notified when someone sends you a teleport request.",
                    p -> p.tpaAlerts, (p, v) -> p.tpaAlerts = v),
            new SettingDef.Toggle("notifications.combat", "notifications", "Combat Alerts",
                    "Show the combat tag countdown above your hotbar.",
                    p -> p.combatAlerts, (p, v) -> p.combatAlerts = v),

            new SettingDef.Toggle("pvp.totems", "pvp", "Totem Particles",
                    "Show the totem animation. Totems still save you either way.",
                    p -> p.totemParticles, (p, v) -> p.totemParticles = v),
            new SettingDef.Toggle("pvp.explosions", "pvp", "Explosion Particles",
                    "Show explosion effects. Explosions that push you always apply.",
                    p -> p.explosionParticles, (p, v) -> p.explosionParticles = v),

            new SettingDef.Choice("privacy.tpa", "privacy", "Who Can TPA You",
                    "Who is allowed to send you teleport requests.",
                    p -> p.tpaRequests, (p, v) -> p.tpaRequests = v),

            new SettingDef.Toggle("general.phantoms", "general", "Phantom Spawning",
                    "Allow phantoms to spawn around you when you have not slept.",
                    p -> p.phantomSpawning, (p, v) -> p.phantomSpawning = v),
            new SettingDef.Toggle("general.pearls", "general", "Keep Ender Pearls On Death",
                    "Keep your thrown ender pearls in flight when you die.",
                    p -> p.keepEnderPearlsOnDeath, (p, v) -> p.keepEnderPearlsOnDeath = v),
            new SettingDef.Toggle("general.nightvision", "general", "Night Vision",
                    "Permanent night vision, with no particles or effect icon.",
                    p -> p.nightVision, (p, v) -> p.nightVision = v));

    private static final Map<String, SettingDef> BY_ID = new LinkedHashMap<>();

    static {
        for (SettingDef setting : SETTINGS) {
            BY_ID.put(setting.id(), setting);
        }
    }

    private SettingsRegistry() {
    }

    public static List<Category> categories() {
        return CATEGORIES;
    }

    public static Category category(String id) {
        for (Category category : CATEGORIES) {
            if (category.id().equals(id)) {
                return category;
            }
        }
        return null;
    }

    public static List<SettingDef> inCategory(String category) {
        List<SettingDef> out = new ArrayList<>();
        for (SettingDef setting : SETTINGS) {
            if (setting.category().equals(category)) {
                out.add(setting);
            }
        }
        return out;
    }

    public static SettingDef byId(String id) {
        return BY_ID.get(id);
    }

    public static List<String> ids() {
        return List.copyOf(BY_ID.keySet());
    }
}
