package dev.auri.tpacombat;

import com.mojang.serialization.JsonOps;
import com.google.gson.JsonPrimitive;
import net.minecraft.dialog.AfterAction;
import net.minecraft.dialog.DialogActionButtonData;
import net.minecraft.dialog.DialogButtonData;
import net.minecraft.dialog.DialogCommonData;
import net.minecraft.dialog.action.DialogAction;
import net.minecraft.dialog.action.DynamicRunCommandDialogAction;
import net.minecraft.dialog.action.ParsedTemplate;
import net.minecraft.dialog.action.SimpleDialogAction;
import net.minecraft.dialog.body.DialogBody;
import net.minecraft.dialog.body.PlainMessageDialogBody;
import net.minecraft.dialog.input.TextInputControl;
import net.minecraft.dialog.type.Dialog;
import net.minecraft.dialog.type.DialogInput;
import net.minecraft.dialog.type.MultiActionDialog;
import net.minecraft.registry.entry.RegistryEntry;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.network.ServerPlayerEntity;
import net.minecraft.text.ClickEvent;
import net.minecraft.text.MutableText;
import net.minecraft.text.Text;
import net.minecraft.util.Formatting;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/**
 * Builds the settings screens as vanilla dialogs.
 *
 * <p>These are constructed per player and opened through {@link RegistryEntry#of}, so each button
 * label can carry that player's current value. A registered datapack dialog would be static and
 * could not show "Public Chat: OFF".
 */
public final class SettingsDialogs {

    private static final int BUTTON_WIDTH = 200;

    private SettingsDialogs() {
    }

    public static void openCategory(ServerPlayerEntity player, PlayerProfile profile, String categoryId) {
        SettingsRegistry.Category category = SettingsRegistry.category(categoryId);
        if (category == null) {
            return;
        }
        if (categoryId.equals("friends")) {
            openFriends(player, profile);
            return;
        }

        // One category per screen, one setting per row: values are never mixed in with navigation.
        List<DialogActionButtonData> buttons = new ArrayList<>();
        for (SettingDef setting : SettingsRegistry.inCategory(categoryId)) {
            buttons.add(settingButton(setting, profile));
        }
        if (categoryId.equals("privacy")) {
            buttons.add(plainButton(
                    Text.literal("Auto Accept List").formatted(Formatting.WHITE),
                    "Players whose teleport requests skip the prompt",
                    "settings autoaccept"));
        }

        open(player, new MultiActionDialog(
                common(title(), List.of(header(category))),
                buttons,
                Optional.of(backButton()),
                1));
    }

    /** The landing screen: just the categories, two to a row. */
    public static void openRoot(ServerPlayerEntity player, PlayerProfile profile) {
        List<DialogActionButtonData> buttons = new ArrayList<>();
        for (SettingsRegistry.Category category : SettingsRegistry.categories()) {
            buttons.add(navButton(category));
        }
        open(player, new MultiActionDialog(
                common(title(), List.of(new PlainMessageDialogBody(
                        Text.literal("Choose a category").formatted(Formatting.GRAY), 260))),
                buttons,
                Optional.of(closeButton()),
                1));
    }

    // ------------------------------------------------------------------ friends

    /** The follow list, with each entry showing that player's head next to their name. */
    public static void openFriends(ServerPlayerEntity player, PlayerProfile profile) {
        MinecraftServer server = player.getEntityWorld().getServer();
        SocialManager social = TpaCombat.social();
        UUID self = player.getUuid();

        List<UUID> shown = switch (profile.friendsFilter) {
            case "following" -> social.following(self);
            case "followers" -> social.followers(self);
            default -> social.friends(self);
        };

        List<DialogActionButtonData> buttons = new ArrayList<>();
        buttons.add(plainButton(
                Text.literal("Filter: ").formatted(Formatting.GRAY)
                        .append(Text.literal(filterLabel(profile.friendsFilter)).formatted(Formatting.WHITE)),
                "Cycle between friends, following and followers",
                "settings friendsfilter"));
        buttons.add(plainButton(
                Text.literal("Search").formatted(Formatting.WHITE),
                "Look up a player by name",
                "settings friendsearch"));

        for (UUID id : shown) {
            buttons.add(playerButton(server, social, id));
        }

        buttons.add(plainButton(
                Text.literal("+ Follow").formatted(Formatting.GREEN),
                "Follow a player by name",
                "settings friendsearch"));

        MutableText counts = Text.empty()
                .append(Text.literal(social.friends(self).size() + " friends").formatted(Formatting.WHITE))
                .append(Text.literal(" / ").formatted(Formatting.DARK_GRAY))
                .append(Text.literal(social.following(self).size() + " following").formatted(Formatting.GRAY));

        open(player, new MultiActionDialog(
                common(title(), List.of(new PlainMessageDialogBody(counts, 260))),
                buttons,
                Optional.of(backButton()),
                1));
    }

    /**
     * The manually built auto-accept list. Entries are addressed by UUID so offline players can be
     * removed, matching the friends list.
     */
    public static void openAutoAccept(ServerPlayerEntity player, PlayerProfile profile) {
        MinecraftServer server = player.getEntityWorld().getServer();
        SocialManager social = TpaCombat.social();

        List<DialogActionButtonData> buttons = new ArrayList<>();
        for (String raw : profile.autoAccept) {
            UUID id;
            try {
                id = UUID.fromString(raw);
            } catch (IllegalArgumentException ignored) {
                continue;
            }
            String name = social.nameOf(server, id);
            ServerPlayerEntity online = server.getPlayerManager().getPlayer(id);
            MutableText label = Text.empty();
            if (online != null) {
                label.append(Icons.head(online.getGameProfile())).append(Text.literal(" "));
            }
            label.append(Text.literal(name).formatted(online != null ? Formatting.WHITE : Formatting.GRAY));
            buttons.add(plainButton(label, "Click to remove from auto accept",
                    "settings autoremove " + id));
        }

        buttons.add(plainButton(Text.literal("+ Add Player").formatted(Formatting.GREEN),
                "Auto-accept a player's teleport requests", "settings autosearch"));

        MutableText counts = Text.empty()
                .append(Text.literal(profile.autoAccept.size() + " auto-accepted").formatted(Formatting.WHITE));

        open(player, new MultiActionDialog(
                common(title(), List.of(
                        new PlainMessageDialogBody(counts, 260),
                        new PlainMessageDialogBody(Text.literal(
                                "Their /tpa and /tpahere are accepted without asking.")
                                .formatted(Formatting.GRAY), 260))),
                buttons,
                Optional.of(backButton("settings privacy")),
                1));
    }

    /** Name entry used by both the friends search and the auto-accept list. */
    public static void openNameEntry(ServerPlayerEntity player, String prompt, String command,
                                     String cancelCommand) {
        DialogInput input = new DialogInput("player_name",
                new TextInputControl(300, Text.literal("Player name").formatted(Formatting.WHITE),
                        true, "", 16, Optional.empty()));

        DialogActionButtonData confirm = new DialogActionButtonData(
                new DialogButtonData(Text.literal("Confirm").formatted(Formatting.GREEN), Optional.empty(), 200),
                template(command + " $(player_name)"));
        DialogActionButtonData cancel = new DialogActionButtonData(
                new DialogButtonData(Text.literal("Cancel").formatted(Formatting.RED), Optional.empty(), 200),
                Optional.of(new SimpleDialogAction(new ClickEvent.RunCommand(cancelCommand))));

        DialogCommonData common = new DialogCommonData(
                title(), Optional.of(Text.literal("Settings")), true, false,
                AfterAction.WAIT_FOR_RESPONSE,
                List.<DialogBody>of(new PlainMessageDialogBody(
                        Text.literal(prompt).formatted(Formatting.GRAY), 260)),
                List.of(input));

        open(player, new MultiActionDialog(common, List.of(confirm, cancel), Optional.empty(), 2));
    }

    /** The name-entry screen behind Search and + Follow. */
    public static void openSearch(ServerPlayerEntity player) {
        DialogInput input = new DialogInput("player_name",
                new TextInputControl(300, Text.literal("Player name").formatted(Formatting.WHITE),
                        true, "", 16, Optional.empty()));

        DialogActionButtonData search = new DialogActionButtonData(
                new DialogButtonData(Text.literal("Search").formatted(Formatting.GREEN), Optional.empty(), 200),
                template("settings finduser $(player_name)"));
        DialogActionButtonData cancel = new DialogActionButtonData(
                new DialogButtonData(Text.literal("Cancel").formatted(Formatting.RED), Optional.empty(), 200),
                Optional.of(new SimpleDialogAction(new ClickEvent.RunCommand("settings friends"))));

        DialogCommonData common = new DialogCommonData(
                title(),
                Optional.of(Text.literal("Settings")),
                true,
                false,
                AfterAction.WAIT_FOR_RESPONSE,
                List.<DialogBody>of(new PlainMessageDialogBody(
                        Icons.item("item/oak_sign").append(Text.literal(" Find a player").formatted(Formatting.GRAY)),
                        260)),
                List.of(input));

        open(player, new MultiActionDialog(common, List.of(search, cancel), Optional.empty(), 2));
    }

    private static String filterLabel(String filter) {
        return switch (filter) {
            case "following" -> "Following";
            case "followers" -> "Followers";
            default -> "Friends";
        };
    }

    private static DialogActionButtonData playerButton(MinecraftServer server, SocialManager social, UUID id) {
        String name = social.nameOf(server, id);
        ServerPlayerEntity online = server.getPlayerManager().getPlayer(id);
        MutableText label = Text.empty();
        if (online != null) {
            label.append(Icons.head(online.getGameProfile())).append(Text.literal(" "));
        }
        label.append(Text.literal(name).formatted(online != null ? Formatting.WHITE : Formatting.GRAY));
        // Addressed by UUID so the button works for offline players too, where the
        // player-argument form of /unfollow cannot resolve a name.
        return plainButton(label, online != null ? "Online - click to unfollow" : "Offline - click to unfollow",
                "settings unfollowid " + id);
    }

    // ------------------------------------------------------------------ shared pieces

    private static DialogBody header(SettingsRegistry.Category category) {
        return new PlainMessageDialogBody(Text.empty()
                .append(Icons.item(category.sprite()))
                .append(Text.literal(" " + category.title()).formatted(Formatting.WHITE)), 260);
    }

    private static Text title() {
        return Text.empty()
                .append(Text.literal(Config.get().tablist.serverName).formatted(Formatting.RED))
                .append(Text.literal(" Settings").formatted(Formatting.GRAY));
    }

    private static DialogActionButtonData settingButton(SettingDef setting, PlayerProfile profile) {
        MutableText label = Text.empty()
                .append(Text.literal(setting.label() + ": ").formatted(Formatting.WHITE))
                .append(setting.valueText(profile));
        DialogButtonData button = new DialogButtonData(label,
                Optional.of(Text.literal(setting.description()).formatted(Formatting.GRAY)), BUTTON_WIDTH);
        return new DialogActionButtonData(button,
                Optional.of(new SimpleDialogAction(new ClickEvent.RunCommand("settings open " + setting.id()))));
    }

    /**
     * One screen per setting, listing every value it can take. The value in force is marked and
     * has no action, so clicking it cannot be mistaken for a change.
     */
    public static void openSetting(ServerPlayerEntity player, PlayerProfile profile, SettingDef setting) {
        String current = setting.currentKey(profile);
        List<DialogActionButtonData> buttons = new ArrayList<>();
        for (String key : setting.optionKeys()) {
            boolean selected = key.equals(current);
            MutableText label = Text.empty()
                    .append(Text.literal(selected ? "\u2714 " : "  ").formatted(Formatting.GREEN))
                    .append(setting.optionLabel(key));
            DialogButtonData button = new DialogButtonData(label,
                    Optional.of(Text.literal(selected ? "Currently selected" : "Click to select")
                            .formatted(Formatting.GRAY)),
                    BUTTON_WIDTH);
            buttons.add(new DialogActionButtonData(button, selected
                    ? Optional.empty()
                    : Optional.of(new SimpleDialogAction(
                            new ClickEvent.RunCommand("settings set " + setting.id() + " " + key)))));
        }

        SettingsRegistry.Category category = SettingsRegistry.category(setting.category());
        List<DialogBody> body = List.of(
                new PlainMessageDialogBody(Text.empty()
                        .append(category == null ? Text.empty() : Icons.item(category.sprite()))
                        .append(Text.literal(" " + setting.label()).formatted(Formatting.WHITE)), 260),
                new PlainMessageDialogBody(
                        Text.literal(setting.description()).formatted(Formatting.GRAY), 260));

        open(player, new MultiActionDialog(
                common(title(), body),
                buttons,
                Optional.of(backButton("settings " + setting.category())),
                1));
    }

    private static DialogActionButtonData navButton(SettingsRegistry.Category category) {
        MutableText label = Text.empty()
                .append(Icons.item(category.sprite()))
                .append(Text.literal(" " + category.title()).formatted(Formatting.GRAY));
        DialogButtonData button = new DialogButtonData(label,
                Optional.of(Text.literal("Open " + category.title()).formatted(Formatting.DARK_GRAY)),
                BUTTON_WIDTH);
        return new DialogActionButtonData(button,
                Optional.of(new SimpleDialogAction(new ClickEvent.RunCommand("settings " + category.id()))));
    }

    private static DialogActionButtonData plainButton(Text label, String tooltip, String command) {
        DialogButtonData button = new DialogButtonData(label,
                Optional.of(Text.literal(tooltip).formatted(Formatting.GRAY)), BUTTON_WIDTH);
        return new DialogActionButtonData(button,
                Optional.of(new SimpleDialogAction(new ClickEvent.RunCommand(command))));
    }

    private static DialogActionButtonData backButton() {
        return backButton("settings");
    }

    private static DialogActionButtonData backButton(String command) {
        return new DialogActionButtonData(
                new DialogButtonData(Text.literal("\u2190 Back").formatted(Formatting.GRAY),
                        Optional.empty(), 200),
                Optional.of(new SimpleDialogAction(new ClickEvent.RunCommand(command))));
    }

    private static DialogActionButtonData closeButton() {
        return new DialogActionButtonData(
                new DialogButtonData(Text.literal("Close").formatted(Formatting.RED), Optional.empty(), 200),
                Optional.empty());
    }

    /** ParsedTemplate has no public constructor, so it is built through its codec. */
    private static Optional<DialogAction> template(String template) {
        return ParsedTemplate.CODEC.parse(JsonOps.INSTANCE, new JsonPrimitive(template))
                .result()
                .map(parsed -> new DynamicRunCommandDialogAction(parsed));
    }

    private static DialogCommonData common(Text title, List<DialogBody> body) {
        return new DialogCommonData(
                title,
                Optional.of(Text.literal("Settings")),
                true,
                false,
                AfterAction.WAIT_FOR_RESPONSE,
                body,
                List.<DialogInput>of());
    }

    private static void open(ServerPlayerEntity player, Dialog dialog) {
        player.openDialog(RegistryEntry.of(dialog));
    }
}
