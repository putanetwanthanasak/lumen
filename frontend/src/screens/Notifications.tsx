/**
 * Screen 5: notifications (DESIGN.md section 7.5), opened from the header bell. The
 * title and body are the backend's own Thai text; the screen adds an icon and a
 * next step per kind. The API keeps no read state, so there is no "new" tag; when
 * the user has more alerts than the API lists, a line says how many.
 */
import { alertAction } from "../alertAction.ts";
import { getBuffer, getNotifications } from "../api.ts";
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
  consolidation_loan: { icon: "bank", badge: "bg-info-bg text-info-ink" },
};

async function loadAlerts(): Promise<{ notifications: NotificationOut[]; count: number; bufferBalance: Money }> {
  const [list, buffer] = await Promise.all([getNotifications(), getBuffer()]);
  return { notifications: list.notifications, count: list.count, bufferBalance: buffer.balance };
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
          <>
            <ul className="flex flex-col gap-3">
              {load.data.notifications.map((n) => (
                <NotificationCard key={n.id} notification={n} bufferBalance={load.data.bufferBalance} />
              ))}
            </ul>
            {load.data.count > load.data.notifications.length && (
              <p className="text-center text-body text-ink-muted">{ALERTS.more(load.data.notifications.length, load.data.count)}</p>
            )}
          </>
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
        <p className="text-body font-bold text-ink">{notification.title}</p>
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
