#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wayland-client.h>

/* KDE's dpms.xml v1 protocol. This client only subscribes to output state. */
static const struct wl_interface dpms_interface = {
    "org_kde_kwin_dpms", 1, 2,
    (const struct wl_message[]){{"set", "u", NULL}, {"release", "", NULL}},
    3, (const struct wl_message[]){{"supported", "u", NULL}, {"mode", "u", NULL}, {"done", "", NULL}},
};
static const struct wl_interface manager_interface = {
    "org_kde_kwin_dpms_manager", 1, 1,
    (const struct wl_message[]){{"get", "no", (const struct wl_interface *[]){&dpms_interface, &wl_output_interface}}},
    0, NULL,
};

static struct wl_proxy *manager;
static struct wl_list outputs;

struct output {
    struct wl_list link;
    uint32_t name;
    struct wl_output *object;
    struct wl_proxy *dpms;
    bool ready;
    uint32_t mode;
};

static void report_state(void)
{
    static const char *previous;
    const char *state = wl_list_empty(&outputs) ? "unknown" : "off";
    struct output *out;
    wl_list_for_each(out, &outputs, link) {
        if (!out->ready || out->mode == 0) {
            state = out->ready ? "on" : "unknown";
            break;
        }
    }
    if (!previous || strcmp(state, previous) != 0) {
        puts(state);
        fflush(stdout);
        previous = state;
    }
}

static void supported(void *data, struct wl_proxy *dpms, uint32_t value)
{
    /* KWin reports mode On for an output without DPMS. */
}

static void mode(void *data, struct wl_proxy *dpms, uint32_t value)
{
    struct output *out = data;
    out->mode = value;
}

static void done(void *data, struct wl_proxy *dpms)
{
    struct output *out = data;
    out->ready = true;
    report_state();
}

static void subscribe(struct output *out)
{
    static const struct {
        void (*supported)(void *, struct wl_proxy *, uint32_t);
        void (*mode)(void *, struct wl_proxy *, uint32_t);
        void (*done)(void *, struct wl_proxy *);
    } listener = {supported, mode, done};
    out->dpms = wl_proxy_marshal_flags(manager, 0, &dpms_interface, 1, 0, NULL, out->object);
    if (!out->dpms || wl_proxy_add_listener(out->dpms, (void (**)(void))&listener, out) < 0) {
        fputs("Cannot subscribe to KDE display power\n", stderr);
        exit(1);
    }
}

static void global(void *data, struct wl_registry *registry, uint32_t name,
                   const char *interface, uint32_t version)
{
    if (strcmp(interface, manager_interface.name) == 0 && !manager) {
        manager = wl_registry_bind(registry, name, &manager_interface, 1);
        if (!manager)
            exit(1);
        struct output *out;
        wl_list_for_each(out, &outputs, link)
            subscribe(out);
    } else if (strcmp(interface, wl_output_interface.name) == 0) {
        struct output *out = calloc(1, sizeof(*out));
        if (!out)
            exit(1);
        out->name = name;
        out->object = wl_registry_bind(registry, name, &wl_output_interface, version < 3 ? version : 3);
        if (!out->object)
            exit(1);
        wl_list_insert(&outputs, &out->link);
        report_state();
        if (manager)
            subscribe(out);
    }
}

static void remove_global(void *data, struct wl_registry *registry, uint32_t name)
{
    struct output *out, *next;
    wl_list_for_each_safe(out, next, &outputs, link) {
        if (out->name != name)
            continue;
        if (out->dpms)
            wl_proxy_marshal_flags(out->dpms, 1, NULL, 1, WL_MARSHAL_FLAG_DESTROY);
        if (wl_output_get_version(out->object) >= WL_OUTPUT_RELEASE_SINCE_VERSION)
            wl_output_release(out->object);
        else
            wl_output_destroy(out->object);
        wl_list_remove(&out->link);
        free(out);
        report_state();
    }
}

int main(void)
{
    static const struct wl_registry_listener listener = {global, remove_global};
    struct wl_display *display = wl_display_connect(NULL);
    if (!display) {
        perror("Cannot connect to Wayland");
        return 1;
    }
    wl_list_init(&outputs);
    wl_registry_add_listener(wl_display_get_registry(display), &listener, NULL);
    if (wl_display_roundtrip(display) < 0 || !manager) {
        fputs("KDE display power events are unavailable\n", stderr);
        return 1;
    }
    while (wl_display_dispatch(display) >= 0)
        ;
    perror("Lost Wayland connection");
    wl_display_disconnect(display);
    return 1;
}
