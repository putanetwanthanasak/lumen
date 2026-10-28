/**
 * Screen 5: notifications (DESIGN.md section 7.5), opened from the header bell. The
 * title and body are the backend's own Thai text; the screen adds an icon and a
 * next step per kind. Opening it marks every notification read; the ones that
 * were unread keep a "ใหม่" tag while the screen is open.
 * TODO(backend): GET /notifications and POST /notifications/read (mock only for now).
 */
import { alertAction } from "../alertAction.ts";
import { getBuffer, getNotifications, markNotificationsRead } from "../api.ts";
import type { NotificationKind, NotificationOut } from "../api-types.ts";
import { ALERTS } from "../copy.ts";
import { Icon, type IconName } from "../components/Icon.tsx";
import { Screen } from "../components/Screen.tsx";
import { Card, ErrorState, Loading } from "../components/ui.tsx";
import type { Money } from "../money.ts";
import { navigate } from "../router.ts";
import { useLoad } from "../useLoad.ts";

const KIND_STYLE: Record<NotificationKind, { icon: IconName; badge: string }> = {
  new_debt: { icon: "bell", badge: "bg-info-bg text-info-ink" },
  cash_withdrawal: { icon: "alert", badge: "bg-risk-bg text-risk-ink" },
  cash_loan: { icon: "alert", badge: "bg-risk-bg text-risk-ink" },
  over_cap: { icon: "alert", badge: "bg-warn-bg text-warn-ink" },
  payday_shortfall: { icon: "alert", badge: "bg-warn-bg text-warn-ink" },
  leftover_saved: { icon: "shield", badge: "bg-ok-bg text-ok-ink" },
};

async function loadAlerts(): Promise<{ notifications: NotificationOut[]; bufferBalance: Money }> {
  const [list, buffer] = await Promise.all([getNotifications(), getBuffer()]);
  // Shown as loaded (unread tagged), then marked read for the bell; a failed mark
  // only leaves the badge up.
  if (list.unread_count > 0) await markNotificationsRead().catch(() => undefined);
  return { notifications: list.notifications, bufferBalance: buffer.balance };
}

export function NotificationsScreen() {
  const [load, reload] = useLoad(loadAlerts);
  return (
    <Screen route="alerts" title={ALERTS.title} back="home">
      {load.state === "loading" && <Loading lines={3} />}
      {load.state === "error" && <ErrorState onRetry={reload} />}
      {load.state === "ready" &&
        (load.data.notifications.length === 0 ? (
          <Card>
            <p className="text-body text-ink-muted">{ALERTS.empty}</p>
          </Card>
        ) : (
          <ul className="flex flex-col gap-3">
            {load.data.notifications.map((n) => (
              <NotificationCard key={n.id} notification={n} bufferBalance={load.data.bufferBalance} />
            ))}
          </ul>
        ))}
    </Screen>
  );
}

function NotificationCard({ notification, bufferBalance }: { notification: NotificationOut; bufferBalance: Money }) {
  const style = KIND_STYLE[notification.kind];
  const action = alertAction(notification.kind, bufferBalance);
  return (
    <li className="flex gap-3 rounded-card bg-card p-4 shadow-card">
      <span className={`inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-pill ${style.badge}`}>
        <Icon name={style.icon} />
      </span>
      <div className="flex min-w-0 flex-col gap-1">
        <p className="flex items-center gap-2 text-body font-bold text-ink">
          {notification.title}
          {!notification.read && (
            <span className="rounded-pill bg-risk-ink px-2 py-0.5 text-caption font-bold text-white">{ALERTS.unread}</span>
          )}
        </p>
        <p className="text-body text-ink">{notification.body}</p>
        {action !== null && (
          <button
            type="button"
            onClick={() => navigate(action.route)}
            className="-ml-2 min-h-11 cursor-pointer self-start rounded-pill px-2 text-body font-semibold text-leaf-800 underline underline-offset-4 hover:bg-leaf-50"
          >
            {action.label}
          </button>
        )}
      </div>
    </li>
  );
}
