import { getEquityStrings } from "../../lib/i18n/equityStrings";
import { useLocale } from "../../hooks/useLocale";
import { formatRs } from "../../lib/equityDisplay";

interface EquityRsBarsProps {
  rs1d: number;
  rs5d: number;
  rs20d: number;
  rs60d: number;
  rs120d: number;
}

function RsBar({ label, value }: { label: string; value: number }) {
  if (!Number.isFinite(value)) {
    return (
      <div className="equity-rs-bar equity-rs-bar--empty">
        <span className="equity-rs-bar__k">{label}</span>
        <span className="equity-rs-bar__v">—</span>
      </div>
    );
  }
  const cap = 15;
  const pct = Math.min(100, (Math.abs(value) / cap) * 100);
  const positive = value >= 0;

  return (
    <div className="equity-rs-bar">
      <span className="equity-rs-bar__k">{label}</span>
      <div className="equity-rs-bar__track">
        <div
          className={`equity-rs-bar__fill ${positive ? "equity-rs-bar__fill--up" : "equity-rs-bar__fill--down"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`equity-rs-bar__v ${positive ? "equity-text-up" : "equity-text-down"}`}>{formatRs(value)}</span>
    </div>
  );
}

export function EquityRsBars(props: EquityRsBarsProps) {
  const { locale } = useLocale();
  const s = getEquityStrings(locale);

  return (
    <div className="equity-rs-bars" aria-label={s.fields.rsChart}>
      <RsBar label={s.fields.rs1d} value={props.rs1d} />
      <RsBar label={s.fields.rs5d} value={props.rs5d} />
      <RsBar label={s.fields.rs20d} value={props.rs20d} />
      <RsBar label={s.fields.rs60d} value={props.rs60d} />
      <RsBar label={s.fields.rs120d} value={props.rs120d} />
    </div>
  );
}
