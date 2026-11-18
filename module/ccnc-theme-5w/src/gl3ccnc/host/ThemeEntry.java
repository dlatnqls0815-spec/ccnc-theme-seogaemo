package gl3ccnc.host;

import gl3ccnc.api.ModEntry;
import hmgapi.hook.LoadedApp;
import hmgapi.hook.ModContext;

/** Entry called by the Seogaemo core hook host. */
public final class ThemeEntry extends hmgapi.hook.ModEntry {
    private ModEntry theme;
    private gl3ccnc.api.ModContext context;

    @Override
    public void zygoteInit(ModContext host) throws Throwable {
        Class<?> entry = Class.forName("dev.ev6.nowplaying.UniversalEntry");
        ModEntry target = entry.asSubclass(ModEntry.class).getConstructor().newInstance();
        gl3ccnc.api.ModContext adapted = new gl3ccnc.api.ModContext(host);
        target.zygoteInit(adapted);
        context = adapted;
        theme = target;
    }

    @Override
    public void appLoaded(ModContext host, LoadedApp app) throws Throwable {
        theme.appLoaded(context, new gl3ccnc.api.LoadedApp(app));
    }
}
