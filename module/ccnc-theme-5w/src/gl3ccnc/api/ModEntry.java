package gl3ccnc.api;

/** Theme lifecycle ABI. The host calls the two boot/app callbacks through ThemeEntry. */
public abstract class ModEntry {
    public void zygoteInit(ModContext mod) throws Throwable {}

    public void appLoaded(ModContext mod, LoadedApp app) throws Throwable {}

    public void onSettingsChanged(ModContext mod) throws Throwable {}

    public void onEnabled(ModContext mod, boolean enabled) throws Throwable {}
}
