package dev.auri.combat.command;

import dev.auri.combat.AuriCombatPlugin;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.TabCompleter;
import org.jetbrains.annotations.NotNull;

import java.util.List;
import java.util.Locale;

/** {@code /auricombat reload}. */
public final class AdminCommand implements CommandExecutor, TabCompleter {

    private final AuriCombatPlugin plugin;

    public AdminCommand(AuriCombatPlugin plugin) {
        this.plugin = plugin;
    }

    @Override
    public boolean onCommand(@NotNull CommandSender sender, @NotNull Command command,
                             @NotNull String label, @NotNull String[] args) {
        if (!sender.hasPermission("auri.admin")) {
            plugin.messages().send(sender, "errors.no-permission");
            return true;
        }
        if (args.length == 0 || !args[0].equalsIgnoreCase("reload")) {
            plugin.messages().send(sender, "errors.usage", "usage", command.getUsage());
            return true;
        }
        plugin.reload();
        plugin.messages().send(sender, "errors.reloaded");
        return true;
    }

    @Override
    public List<String> onTabComplete(@NotNull CommandSender sender, @NotNull Command command,
                                      @NotNull String label, @NotNull String[] args) {
        if (args.length == 1 && "reload".startsWith(args[0].toLowerCase(Locale.ROOT))) {
            return List.of("reload");
        }
        return List.of();
    }
}
