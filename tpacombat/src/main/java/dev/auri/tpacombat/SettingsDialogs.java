package dev.auri.tpacombat;

import net.minecraft.dialog.AfterAction;
import net.minecraft.dialog.DialogActionButtonData;
import net.minecraft.dialog.DialogButtonData;
import net.minecraft.dialog.DialogCommonData;
import net.minecraft.dialog.action.SimpleDialogAction;
import net.minecraft.dialog.body.DialogBody;
import net.minecraft.dialog.body.PlainMessageDialogBody;
import net.minecraft.dialog.type.Dialog;
import net.minecraft.dialog.type.DialogInput;
import net.minecraft.dialog.type.MultiActionDialog;
import net.minecraft.registry.entry.RegistryEntry;
import net.minecraft.server.network.ServerPlayerEntity;
import net.minecraft.text.ClickEvent;
import net.minecraft.text.MutableText;
import net.minecraft.text.Text;
import net.minecraft.util.Formatting;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * Builds the settings screens as vanilla dialogs.
 *
 * <p>These are constructed per player and opened through {@link RegistryEntry#of}, so each button
 * label can carry that player's current value. A registered datapack dialog would be static and
 * could not show "Public Chat: OFF".
 */
public final class SettingsDialogs {

    private static final int BUTTON_WIDTH = 260;

    private SettingsDialogs() {
    }

    public static void openCategory(ServerPlayerEntity player, PlayerProfile profile, String categoryId) {
        SettingsRegistry.Category category = SettingsRegistry.category(categoryId);
        if (category == null) {
            return;
        }

        List<DialogActionButtonData> buttons = new ArrayList<>();
        for (SettingDef setting : SettingsRegistry.inCategory(categoryId)) {
            buttons.add(settingButton(setting, profile));
        }
        if (categoryId.equals("social")) {
            // Social has no toggles of its own; it is a shortcut to the follow lists.
            buttons.add(commandButton("Friends", "See who follows you back", "friends"));
            buttons.add(commandButton("Following", "People you follow", "following"));
            buttons.add(commandButton("Followers", "People who follow you", "followers"));
        }
        // Other categories become navigation rows, mirroring the in-game settings layout.
        for (SettingsRegistry.Category other : SettingsRegistry.categories()) {
            if (!other.id().equals(categoryId)) {
                buttons.add(navButton(other));
            }
        }

        Text title = Text.empty()
                .append(Text.literal(Config.get().tablist.serverName).formatted(Formatting.RED, Formatting.BOLD))
                .append(Text.literal(" Settings").formatted(Formatting.GRAY));

        DialogBody body = new PlainMessageDialogBody(
                Text.literal(category.icon() + " " + category.title()).formatted(Formatting.WHITE), 260);

        open(player, new MultiActionDialog(
                common(title, List.of(body)),
                buttons,
                Optional.of(closeButton()),
                1));
    }

    /** Entry point shown when /settings is run with no category. */
    public static void openRoot(ServerPlayerEntity player, PlayerProfile profile) {
        openCategory(player, profile, SettingsRegistry.categories().get(0).id());
    }

    private static DialogActionButtonData settingButton(SettingDef setting, PlayerProfile profile) {
        MutableText label = Text.empty()
                .append(Text.literal(setting.label() + ": ").formatted(Formatting.WHITE))
                .append(setting.valueText(profile));
        DialogButtonData button = new DialogButtonData(label,
                Optional.of(Text.literal("Click to toggle").formatted(Formatting.GRAY)), BUTTON_WIDTH);
        return new DialogActionButtonData(button,
                Optional.of(new SimpleDialogAction(new ClickEvent.RunCommand("settings cycle " + setting.id()))));
    }

    /** Runs a chat command and closes, since the output lands in chat rather than a dialog. */
    private static DialogActionButtonData commandButton(String label, String tooltip, String command) {
        DialogButtonData button = new DialogButtonData(
                Text.literal(label).formatted(Formatting.WHITE),
                Optional.of(Text.literal(tooltip).formatted(Formatting.GRAY)), BUTTON_WIDTH);
        return new DialogActionButtonData(button,
                Optional.of(new SimpleDialogAction(new ClickEvent.RunCommand(command))));
    }

    private static DialogActionButtonData navButton(SettingsRegistry.Category category) {
        DialogButtonData button = new DialogButtonData(
                Text.literal(category.icon() + " " + category.title()).formatted(Formatting.GRAY),
                Optional.of(Text.literal("Open " + category.title()).formatted(Formatting.DARK_GRAY)),
                BUTTON_WIDTH);
        return new DialogActionButtonData(button,
                Optional.of(new SimpleDialogAction(new ClickEvent.RunCommand("settings " + category.id()))));
    }

    private static DialogActionButtonData closeButton() {
        return new DialogActionButtonData(
                new DialogButtonData(Text.literal("Close").formatted(Formatting.RED), Optional.empty(), 200),
                Optional.empty());
    }

    /**
     * WAIT_FOR_RESPONSE keeps the client on a holding screen until the command re-opens the menu,
     * so cycling a value looks like the row updating in place instead of the menu closing.
     */
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
