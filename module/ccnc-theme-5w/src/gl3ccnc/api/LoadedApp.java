package gl3ccnc.api;

import android.content.Context;

public final class LoadedApp {
    public final String packageName;
    public final ClassLoader classLoader;
    public final Context context;

    public LoadedApp(hmgapi.hook.LoadedApp app) {
        packageName = app.packageName;
        classLoader = app.classLoader;
        context = app.context;
    }
}
