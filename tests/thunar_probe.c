/* In-process GTK inspection of a disposable Thunar session, never the desktop session. */
#include <gtk/gtk.h>
#include <dlfcn.h>

static GtkWidget *main_window;
static const char *scenario;

static GtkWidget *find_type(GtkWidget *w, const char *type) {
  if (g_str_equal(G_OBJECT_TYPE_NAME(w), type)) return w;
  if (GTK_IS_CONTAINER(w)) {
    GList *children = gtk_container_get_children(GTK_CONTAINER(w));
    GtkWidget *found = NULL;
    for (GList *l = children; l && !found; l = l->next) found = find_type(l->data, type);
    g_list_free(children);
    return found;
  }
  return NULL;
}

static void inspect(GtkWidget *w, int depth) {
  if (GTK_IS_MENU(w)) {
    GdkRGBA background;
    gtk_style_context_get_background_color(gtk_widget_get_style_context(w), GTK_STATE_FLAG_NORMAL, &background);
    g_assert_cmpfloat_with_epsilon(background.alpha, 1.0, 0.001);
    g_assert_cmpfloat_with_epsilon(gtk_widget_get_opacity(w), 1.0, 0.001);
  }
  GtkStyleContextPrintFlags flags = g_str_equal(G_OBJECT_TYPE_NAME(w), "ThunarLocationButtons") ? GTK_STYLE_CONTEXT_PRINT_RECURSE : 0;
  char *style = gtk_style_context_to_string(gtk_widget_get_style_context(w), flags);
  g_print("%*s%s %s\n", depth * 2, "", G_OBJECT_TYPE_NAME(w), style);
  g_free(style);
  if (GTK_IS_CONTAINER(w)) {
    GList *children = gtk_container_get_children(GTK_CONTAINER(w));
    for (GList *l = children; l; l = l->next) inspect(l->data, depth + 1);
    g_list_free(children);
  }
}

static gboolean capture(gpointer unused) {
  GList *windows = gtk_window_list_toplevels();
  for (GList *l = windows; l; l = l->next) g_object_ref(l->data);
  int count = 0;
  for (GList *l = windows; l; l = l->next) {
    GtkWidget *w = l->data;
    if (!gtk_widget_get_mapped(w)) continue;
    inspect(w, 0);
    int width = gtk_widget_get_allocated_width(w), height = gtk_widget_get_allocated_height(w);
    if (GTK_IS_MESSAGE_DIALOG(w)) g_assert_cmpint(width, >=, 320);
    cairo_surface_t *surface = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, width, height);
    cairo_t *cr = cairo_create(surface);
    gtk_widget_draw(w, cr);
    char *name = g_strdup_printf("%s/%s-%d.png", g_getenv("HIKAIDE_OUTPUT"), scenario, count++);
    g_assert_cmpint(cairo_surface_write_to_png(surface, name), ==, CAIRO_STATUS_SUCCESS);
    g_print("CAPTURE %s\n", name);
    g_free(name);
    cairo_destroy(cr);
    cairo_surface_destroy(surface);
  }
  g_assert_cmpint(count, >, 0);
  if (g_str_equal(scenario, "properties") || g_str_equal(scenario, "preferences") ||
      g_str_equal(scenario, "create-folder") || g_str_equal(scenario, "rename") ||
      g_str_equal(scenario, "open-with") || g_str_equal(scenario, "delete-confirm") ||
      g_str_equal(scenario, "context-menu"))
    g_assert_cmpint(count, >=, 2);
  for (GList *l = windows; l; l = l->next) {
    if (GTK_IS_DIALOG(l->data)) gtk_dialog_response(GTK_DIALOG(l->data), GTK_RESPONSE_CLOSE);
    GtkWidget *menu = find_type(l->data, "ThunarMenu");
    if (menu) {
      gtk_menu_shell_deactivate(GTK_MENU_SHELL(menu));
      gtk_menu_popdown(GTK_MENU(menu));
    }
  }
  g_list_free_full(windows, g_object_unref);
  g_assert_nonnull(g_application_get_default());
  g_application_quit(g_application_get_default());
  return G_SOURCE_REMOVE;
}

static void action(const char *name) {
  GtkAccelKey entry;
  g_assert_true(gtk_accel_map_lookup_entry(name, &entry));
  if (entry.accel_key == 0) {
    g_assert_true(gtk_accel_map_change_entry(name, GDK_KEY_F12, 0, TRUE));
    entry.accel_key = GDK_KEY_F12;
    entry.accel_mods = 0;
  }
  g_print("ACTION %s\n", name);
  g_assert_true(gtk_accel_groups_activate(G_OBJECT(main_window), entry.accel_key, entry.accel_mods));
}

static void select_file(void) {
  GtkWidget *view = find_type(main_window, "ExoIconView");
  g_assert_nonnull(view);
  void (*select_path)(gpointer, GtkTreePath *) = dlsym(RTLD_DEFAULT, "exo_icon_view_select_path");
  g_assert_nonnull(select_path);
  GtkTreePath *path = gtk_tree_path_new_from_indices(2, -1);
  select_path(view, path);
  gtk_tree_path_free(path);
  gtk_widget_grab_focus(view);
}

/* Exo paints the drag rectangle with a class on the view itself. */
static void check_rubberband(void) {
  GtkWidget *view = find_type(main_window, "ExoIconView"); /* Real Thunar icon view. */
  g_assert_nonnull(view);
  GtkStyleContext *context = gtk_widget_get_style_context(view); /* Exo's rectangle drawing context. */
  /* Cover pointer, selection and window focus states. */
  const GtkStateFlags states[] = {GTK_STATE_FLAG_NORMAL, GTK_STATE_FLAG_FOCUSED, GTK_STATE_FLAG_PRELIGHT,
                                 GTK_STATE_FLAG_SELECTED, GTK_STATE_FLAG_ACTIVE, GTK_STATE_FLAG_BACKDROP,
                                 GTK_STATE_FLAG_SELECTED | GTK_STATE_FLAG_BACKDROP};
  for (guint i = 0; i < G_N_ELEMENTS(states); i++) { /* Check each drawing state. */
    GdkRGBA fill, border; /* Rectangle fill and outline colors. */
    GtkBorder widths; /* Visible outline thickness. */
    gtk_style_context_save(context);
    gtk_style_context_set_state(context, states[i]);
    gtk_style_context_add_class(context, GTK_STYLE_CLASS_RUBBERBAND);
    gtk_style_context_get_background_color(context, states[i], &fill);
    gtk_style_context_get_border_color(context, states[i], &border);
    gtk_style_context_get_border(context, states[i], &widths);
    g_assert_cmpfloat(fill.alpha, >, 0.1);
    g_assert_cmpfloat(border.alpha, >, 0.4);
    g_assert_cmpint(widths.top, ==, 1);
    gtk_style_context_restore(context);
  }
}

static gboolean exercise(gpointer unused) {
  GList *windows = gtk_window_list_toplevels();
  for (GList *l = windows; l; l = l->next)
    if (g_str_equal(G_OBJECT_TYPE_NAME(l->data), "ThunarWindow")) main_window = l->data;
  g_list_free(windows);
  g_assert_nonnull(main_window);
  char *desktop_font;
  g_object_get(gtk_settings_get_default(), "gtk-font-name", &desktop_font, NULL);
  PangoFontDescription *desktop_description = pango_font_description_from_string(desktop_font);
  const PangoFontDescription *window_font = gtk_style_context_get_font(gtk_widget_get_style_context(main_window), GTK_STATE_FLAG_NORMAL);
  g_assert_cmpfloat_with_epsilon((double)pango_font_description_get_size(window_font) / pango_font_description_get_size(desktop_description), 0.9, 0.01);
  pango_font_description_free(desktop_description);
  g_free(desktop_font);
  GdkRGBA bg;
  gtk_style_context_get_background_color(gtk_widget_get_style_context(main_window), GTK_STATE_FLAG_NORMAL, &bg);
  g_assert_cmpfloat_with_epsilon(bg.red, 16.0 / 255, 0.001);
  g_assert_cmpfloat_with_epsilon(bg.green, bg.red, 0.001);
  g_assert_cmpfloat_with_epsilon(bg.blue, bg.red, 0.001);
  action("<Actions>/ThunarWindow/view-as-icons");
  check_rubberband();
  /* Schedule before actions: modal dialogs enter their own main loop. */
  g_timeout_add(700, capture, NULL);
  if (g_str_equal(scenario, "detailed")) {
    action("<Actions>/ThunarWindow/view-as-detailed-list");
    g_assert_nonnull(find_type(main_window, "ThunarDetailsView"));
  } else if (g_str_equal(scenario, "compact")) {
    action("<Actions>/ThunarWindow/view-as-compact-list");
    g_assert_nonnull(find_type(main_window, "ThunarCompactView"));
  } else if (g_str_equal(scenario, "tabs")) {
    action("<Actions>/ThunarWindow/new-tab");
  } else if (g_str_equal(scenario, "pathbar")) {
    action("<Actions>/ThunarWindow/view-location-selector-buttons");
    g_assert_nonnull(find_type(main_window, "ThunarLocationButtons"));
  } else if (g_str_equal(scenario, "location")) {
    action("<Actions>/ThunarWindow/open-location");
    g_assert_nonnull(find_type(main_window, "ThunarPathEntry"));
  } else if (g_str_equal(scenario, "hidden")) {
    action("<Actions>/ThunarWindow/show-hidden");
  } else if (g_str_equal(scenario, "preferences")) {
    action("<Actions>/ThunarWindow/preferences");
  } else if (g_str_equal(scenario, "create-folder")) {
    action("<Actions>/ThunarStandardView/create-folder");
  } else if (g_str_equal(scenario, "multi-select")) {
    action("<Actions>/ThunarStandardView/select-all-files");
  } else if (!g_str_equal(scenario, "icons") && !g_str_equal(scenario, "empty")) {
    select_file();
    if (g_str_equal(scenario, "properties")) action("<Actions>/ThunarStandardView/properties");
    else if (g_str_equal(scenario, "rename")) action("<Actions>/ThunarStandardView/rename");
    else if (g_str_equal(scenario, "open-with")) action("<Actions>/ThunarActionManager/open-with-other");
    else if (g_str_equal(scenario, "delete-confirm")) action("<Actions>/ThunarActionManager/delete-2");
    else if (g_str_equal(scenario, "backdrop")) gtk_widget_set_state_flags(main_window, GTK_STATE_FLAG_BACKDROP, FALSE);
    else if (g_str_equal(scenario, "context-menu")) {
      GtkWidget *view = find_type(main_window, "ExoIconView");
      GdkEvent *event = gdk_event_new(GDK_KEY_PRESS);
      event->key.window = g_object_ref(gtk_widget_get_window(view));
      event->key.keyval = GDK_KEY_Menu;
      event->key.time = GDK_CURRENT_TIME;
      gdk_event_set_device(event, gdk_seat_get_keyboard(gdk_display_get_default_seat(gtk_widget_get_display(view))));
      gtk_main_do_event(event);
      gdk_event_free(event);
    }
  }
  return G_SOURCE_REMOVE;
}

G_MODULE_EXPORT void gtk_module_init(gint *argc, gchar ***argv) {
  scenario = g_getenv("HIKAIDE_SCENARIO");
  g_assert_nonnull(scenario);
  g_assert_nonnull(g_getenv("HIKAIDE_OUTPUT"));
  g_timeout_add(900, exercise, NULL);
}
