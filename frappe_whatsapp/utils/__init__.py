"""Run on each event."""
import frappe

from frappe.core.doctype.server_script.server_script_utils import EVENT_MAP


def run_server_script_for_doc_event(doc, event):
    """Run on each event."""
    if event not in EVENT_MAP:
        return

    if frappe.flags.in_install:
        return

    if frappe.flags.in_migrate:
        return
    
    if frappe.flags.in_uninstall:
        return

    notification = get_notifications_map().get(
        doc.doctype, {}
    ).get(EVENT_MAP[event], None)

    if notification:
        # run all scripts for this doctype + event
        for notification_name in notification:
            _schedule_whatsapp_notification(notification_name, doc)


def _schedule_whatsapp_notification(notification_name, doc):
    """Schedule WhatsApp notification to run after commit.

    Frappe v16 disallows frappe.db.commit() in doc hooks, so we defer
    the API call to after the transaction commits. This ensures share
    keys (for document print attachments) are persisted before the
    WhatsApp message containing their URL is sent to Meta.

    On Frappe v14/v15, after_commit is not available, so we call directly.
    """
    if hasattr(frappe.db, "after_commit"):
        # Frappe v16+: run after the doc-event transaction commits so that
        # share keys / set-property-after-alert writes are visible to Meta,
        # and commit our own writes (WhatsApp Message + Notification Log)
        # since we are outside the request's auto-commit scope.
        frappe.db.after_commit.add(
            lambda: _send_whatsapp_notification(
                notification_name, doc.doctype, doc.name, commit=True
            )
        )
    else:
        # Frappe v14/v15
        _send_whatsapp_notification(notification_name, doc.doctype, doc.name)


def _send_whatsapp_notification(notification_name, doctype, docname, commit=False):
    """Send WhatsApp notification."""
    try:
        doc = frappe.get_doc(doctype, docname)
        frappe.get_doc(
            "WhatsApp Notification",
            notification_name
        ).send_template_message(doc)
        if commit:
            # nosemgrep: frappe-manual-commit -- runs in after_commit callback outside request scope; WhatsApp Message + Notification Log rows rely on this to persist
            frappe.db.commit()
    except Exception:
        if commit:
            frappe.db.rollback()
        frappe.log_error(
            title=f"WhatsApp Notification failed: {notification_name}"
        )


NOTIFICATION_MAP_CACHE_KEY = "whatsapp_notification_map"


def get_notifications_map():
    """Get mapping of DocType -> event -> notification names.

    Read from cache; the table is only queried when the cache is empty.
    WhatsApp Notification clears the key on update, rename and trash.
    """
    if frappe.flags.in_patch and not frappe.db.table_exists("WhatsApp Notification"):
        return {}

    return frappe.cache().get_value(
        NOTIFICATION_MAP_CACHE_KEY, generator=_build_notifications_map
    ) or {}


def clear_notifications_map_cache():
    """Drop the cached notifications map so the next event rebuilds it.

    Cleared now, and again after commit or rollback where Frappe supports
    it, so another worker cannot cache the map from before the commit, and
    a rolled-back notification does not stay in the cache.
    """
    frappe.cache().delete_value(NOTIFICATION_MAP_CACHE_KEY)
    for callbacks in ("after_commit", "after_rollback"):
        manager = getattr(frappe.db, callbacks, None)
        if manager is not None:
            manager.add(_delete_notifications_map_cache)


def _delete_notifications_map_cache():
    frappe.cache().delete_value(NOTIFICATION_MAP_CACHE_KEY)


def _build_notifications_map():
    """Build the mapping from enabled DocType Event notifications."""
    notification_map = {}
    enabled_whatsapp_notifications = frappe.get_all(
        "WhatsApp Notification",
        fields=("name", "reference_doctype", "doctype_event", "notification_type"),
        filters={"disabled": 0},
    )
    for notification in enabled_whatsapp_notifications:
        if notification.notification_type == "DocType Event":
            notification_map.setdefault(
                notification.reference_doctype, {}
            ).setdefault(
                notification.doctype_event, []
            ).append(notification.name)

    return notification_map


def trigger_whatsapp_notifications_all():
    """Run all."""
    trigger_whatsapp_notifications("All")


def trigger_whatsapp_notifications_hourly():
    """Run hourly."""
    trigger_whatsapp_notifications("Hourly")


def trigger_whatsapp_notifications_daily():
    """Run daily."""
    trigger_whatsapp_notifications("Daily")


def trigger_whatsapp_notifications_weekly():
    """Trigger notification."""
    trigger_whatsapp_notifications("Weekly")


def trigger_whatsapp_notifications_monthly():
    """Trigger notification."""
    trigger_whatsapp_notifications("Monthly")


def trigger_whatsapp_notifications_yearly():
    """Trigger notification."""
    trigger_whatsapp_notifications("Yearly")


def trigger_whatsapp_notifications_hourly_long():
    """Trigger notification."""
    trigger_whatsapp_notifications("Hourly Long")


def trigger_whatsapp_notifications_daily_long():
    """Trigger notification."""
    trigger_whatsapp_notifications("Daily Long")


def trigger_whatsapp_notifications_weekly_long():
    """Trigger notification."""
    trigger_whatsapp_notifications("Weekly Long")


def trigger_whatsapp_notifications_monthly_long():
    """Trigger notification."""
    trigger_whatsapp_notifications("Monthly Long")


def trigger_whatsapp_notifications(event):
    """Run cron."""
    wa_notify_list = frappe.get_list(
        "WhatsApp Notification",
        filters={
            "event_frequency": event,
            "disabled": 0,
        }
    )

    for wa in wa_notify_list:
        frappe.get_doc(
            "WhatsApp Notification",
            wa.name,
        ).send_scheduled_message()

def get_whatsapp_account(phone_id=None, account_type='incoming'):
    """map whatsapp account with message"""
    if phone_id:
        account_name = frappe.db.get_value('WhatsApp Account', {'phone_id': phone_id}, 'name')
        if account_name:
            return frappe.get_doc("WhatsApp Account", account_name)

    account_field_type = 'is_default_incoming' if account_type =='incoming' else 'is_default_outgoing' 
    default_account_name = frappe.db.get_value('WhatsApp Account', {account_field_type: 1}, 'name')
    if default_account_name:
        return frappe.get_doc("WhatsApp Account", default_account_name)

    return None

def format_number(number):
    """Format number."""
    if number.startswith("+"):
        number = number[1 : len(number)]

    return number