package dev.auri.tpacombat;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * The single source of truth for what appears in the settings menu. Both the dialog and the
 * /settings command read this, so adding a setting here adds it to both.
 */
public final class SettingsRegistry {

    public record Category(String id, String title, String icon) {
    }

    private static final List<Category> CATEGORIES = List.of(
            new Category("chat", "Chat", "💬"),
            new Category("notifications", "Notifications", "🔔"),
            new Category("pvp", "PvP", "⚔"),
            new Category("privacy", "Privacy", "🔒"),
            new Category("social", "Social", "👥"));

    private static final List<SettingDef> SETTINGS = List.of(
            new SettingDef.Toggle("chat.public", "chat", "Public Chat",
                    p -> p.publicChat, (p, v) -> p.publicChat = v),
            new SettingDef.Choice("chat.private", "chat", "Private Messages",
                    p -> p.privateMessages, (p, v) -> p.privateMessages = v),
            new SettingDef.Toggle("chat.server", "chat", "Server Messages",
                    p -> p.serverMessages, (p, v) -> p.serverMessages = v),
            new SettingDef.Toggle("chat.death", "chat", "Death Messages",
                    p -> p.deathMessages, (p, v) -> p.deathMessages = v),
            new SettingDef.Toggle("chat.advancement", "chat", "Advancement Messages",
                    p -> p.advancementMessages, (p, v) -> p.advancementMessages = v),
            new SettingDef.Toggle("chat.joinleave", "chat", "Join/Leave Messages",
                    p -> p.joinLeaveMessages, (p, v) -> p.joinLeaveMessages = v),

            new SettingDef.Toggle("notifications.tpa", "notifications", "TPA Alerts",
                    p -> p.tpaAlerts, (p, v) -> p.tpaAlerts = v),
            new SettingDef.Toggle("notifications.combat", "notifications", "Combat Alerts",
                    p -> p.combatAlerts, (p, v) -> p.combatAlerts = v),

            new SettingDef.Toggle("pvp.totems", "pvp", "Totem Particles",
                    p -> p.totemParticles, (p, v) -> p.totemParticles = v),
            new SettingDef.Toggle("pvp.explosions", "pvp", "Explosion Particles",
                    p -> p.explosionParticles, (p, v) -> p.explosionParticles = v),

            new SettingDef.Choice("privacy.tpa", "privacy", "Who Can TPA You",
                    p -> p.tpaRequests, (p, v) -> p.tpaRequests = v));

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
