package dev.auri.combat;

import dev.auri.combat.combat.AttackerResolver;
import dev.auri.combat.combat.CombatListener;
import dev.auri.combat.combat.CombatManager;
import dev.auri.combat.combat.CommandBlocker;
import dev.auri.combat.command.AdminCommand;
import dev.auri.combat.command.TpaCommands;
import dev.auri.combat.config.AuriConfig;
import dev.auri.combat.config.Messages;
import dev.auri.combat.tpa.TpaListener;
import dev.auri.combat.tpa.TpaManager;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.PluginCommand;
import org.bukkit.command.TabCompleter;
import org.bukkit.plugin.java.JavaPlugin;

public final class AuriCombatPlugin extends JavaPlugin {

    private volatile AuriConfig config;
    private final Messages messages = new Messages();

    private CombatManager combatManager;
    private TpaManager tpaManager;
    private AttackerResolver attackerResolver;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        loadConfiguration();

        attackerResolver = new AttackerResolver();
        combatManager = new CombatManager(this);
        tpaManager = new TpaManager(this, combatManager);

        combatManager.start();
        tpaManager.start();

        getServer().getPluginManager().registerEvents(
                new CombatListener(this, combatManager, attackerResolver), this);
        getServer().getPluginManager().registerEvents(new CommandBlocker(this, combatManager), this);
        getServer().getPluginManager().registerEvents(new TpaListener(this, tpaManager), this);

        register("tpa", new TpaCommands.Tpa(this));
        register("tpahere", new TpaCommands.TpaHere(this));
        register("tpaccept", new TpaCommands.Accept(this));
        register("tpdeny", new TpaCommands.Deny(this));
        register("tpacancel", new TpaCommands.Cancel(this));
        register("tpatoggle", new TpaCommands.Toggle(this));
        register("tpaguitoggle", new TpaCommands.GuiToggle(this));
        register("auricombat", new AdminCommand(this));

        getLogger().info("Enabled — combat tag " + config.combat().duration()
                + "s, TPA requests expire after " + config.tpa().requestExpire() + "s.");
    }

    @Override
    public void onDisable() {
        if (combatManager != null) {
            combatManager.stop();
        }
        if (tpaManager != null) {
            tpaManager.stop();
        }
        if (attackerResolver != null) {
            attackerResolver.clear();
        }
    }

    /** Re-reads config.yml. Live tags and pending requests survive; new values apply from here on. */
    public void reload() {
        reloadConfig();
        loadConfiguration();
    }

    private void loadConfiguration() {
        config = AuriConfig.from(getConfig());
        messages.load(getConfig());
    }

    private void register(String name, CommandExecutor executor) {
        PluginCommand command = getCommand(name);
        if (command == null) {
            getLogger().warning("Command /" + name + " is missing from plugin.yml — skipping.");
            return;
        }
        command.setExecutor(executor);
        if (executor instanceof TabCompleter completer) {
            command.setTabCompleter(completer);
        }
    }

    public AuriConfig config() {
        return config;
    }

    public Messages messages() {
        return messages;
    }

    public CombatManager combat() {
        return combatManager;
    }

    public TpaManager tpa() {
        return tpaManager;
    }
}
