package dev.auri.combat.command;

import dev.auri.combat.AuriCombatPlugin;
import dev.auri.combat.tpa.TpaRequest;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.TabCompleter;
import org.bukkit.entity.Player;
import org.jetbrains.annotations.NotNull;

import java.util.List;
import java.util.Locale;

/** The player-facing TPA commands. Each is a thin shell over {@link dev.auri.combat.tpa.TpaManager}. */
public final class TpaCommands {

    private TpaCommands() {
    }

    /** Shared plumbing: player-only enforcement and online-player tab completion. */
    private abstract static class Base implements CommandExecutor, TabCompleter {
        protected final AuriCombatPlugin plugin;

        protected Base(AuriCombatPlugin plugin) {
            this.plugin = plugin;
        }

        @Override
        public boolean onCommand(@NotNull CommandSender sender, @NotNull Command command,
                                 @NotNull String label, @NotNull String[] args) {
            if (!(sender instanceof Player player)) {
                plugin.messages().send(sender, "errors.player-only");
                return true;
            }
            run(player, command, args);
            return true;
        }

        protected abstract void run(Player player, Command command, String[] args);

        @Override
        public List<String> onTabComplete(@NotNull CommandSender sender, @NotNull Command command,
                                          @NotNull String label, @NotNull String[] args) {
            return List.of();
        }

        protected List<String> onlinePlayers(CommandSender sender, String[] args) {
            if (args.length != 1) {
                return List.of();
            }
            String prefix = args[0].toLowerCase(Locale.ROOT);
            return plugin.getServer().getOnlinePlayers().stream()
                    .filter(p -> !p.equals(sender))
                    .map(Player::getName)
                    .filter(name -> name.toLowerCase(Locale.ROOT).startsWith(prefix))
                    .sorted()
                    .toList();
        }

        /** Resolves a target name, reporting the miss to the sender. */
        protected Player resolveTarget(Player sender, Command command, String[] args) {
            if (args.length < 1) {
                plugin.messages().send(sender, "errors.usage", "usage", command.getUsage());
                return null;
            }
            Player target = plugin.getServer().getPlayerExact(args[0]);
            if (target == null || !target.isOnline()) {
                plugin.messages().send(sender, "errors.player-not-found");
                return null;
            }
            return target;
        }
    }

    /** {@code /tpa <player>} — travel to them. */
    public static final class Tpa extends Base {
        public Tpa(AuriCombatPlugin plugin) {
            super(plugin);
        }

        @Override
        protected void run(Player player, Command command, String[] args) {
            Player target = resolveTarget(player, command, args);
            if (target != null) {
                plugin.tpa().send(player, target, TpaRequest.Type.TO_TARGET);
            }
        }

        @Override
        public List<String> onTabComplete(@NotNull CommandSender sender, @NotNull Command command,
                                          @NotNull String label, @NotNull String[] args) {
            return onlinePlayers(sender, args);
        }
    }

    /** {@code /tpahere <player>} — summon them to you. */
    public static final class TpaHere extends Base {
        public TpaHere(AuriCombatPlugin plugin) {
            super(plugin);
        }

        @Override
        protected void run(Player player, Command command, String[] args) {
            Player target = resolveTarget(player, command, args);
            if (target != null) {
                plugin.tpa().send(player, target, TpaRequest.Type.TO_SENDER);
            }
        }

        @Override
        public List<String> onTabComplete(@NotNull CommandSender sender, @NotNull Command command,
                                          @NotNull String label, @NotNull String[] args) {
            return onlinePlayers(sender, args);
        }
    }

    /** {@code /tpaccept [player]} — the optional name disambiguates a queue of requests. */
    public static final class Accept extends Base {
        public Accept(AuriCombatPlugin plugin) {
            super(plugin);
        }

        @Override
        protected void run(Player player, Command command, String[] args) {
            plugin.tpa().accept(player, args.length > 0 ? args[0] : null);
        }

        @Override
        public List<String> onTabComplete(@NotNull CommandSender sender, @NotNull Command command,
                                          @NotNull String label, @NotNull String[] args) {
            return onlinePlayers(sender, args);
        }
    }

    /** {@code /tpdeny [player]}. */
    public static final class Deny extends Base {
        public Deny(AuriCombatPlugin plugin) {
            super(plugin);
        }

        @Override
        protected void run(Player player, Command command, String[] args) {
            plugin.tpa().deny(player, args.length > 0 ? args[0] : null);
        }

        @Override
        public List<String> onTabComplete(@NotNull CommandSender sender, @NotNull Command command,
                                          @NotNull String label, @NotNull String[] args) {
            return onlinePlayers(sender, args);
        }
    }

    /** {@code /tpacancel} — withdraw your outgoing request. */
    public static final class Cancel extends Base {
        public Cancel(AuriCombatPlugin plugin) {
            super(plugin);
        }

        @Override
        protected void run(Player player, Command command, String[] args) {
            plugin.tpa().cancel(player);
        }
    }

    /** {@code /tpatoggle} — stop receiving requests entirely. */
    public static final class Toggle extends Base {
        public Toggle(AuriCombatPlugin plugin) {
            super(plugin);
        }

        @Override
        protected void run(Player player, Command command, String[] args) {
            plugin.tpa().toggleRequests(player);
        }
    }

    /** {@code /tpaguitoggle} — swap between the menu popup and plain clickable chat. */
    public static final class GuiToggle extends Base {
        public GuiToggle(AuriCombatPlugin plugin) {
            super(plugin);
        }

        @Override
        protected void run(Player player, Command command, String[] args) {
            plugin.tpa().toggleGui(player);
        }
    }
}
