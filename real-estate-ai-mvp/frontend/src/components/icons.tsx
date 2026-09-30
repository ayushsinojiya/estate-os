import type { CSSProperties, HTMLAttributes } from "react";

type IconProps = Omit<HTMLAttributes<HTMLSpanElement>, "children"> & {
  size?: number;
  strokeWidth?: number;
  absoluteStrokeWidth?: boolean;
};

function materialIcon(symbol: string) {
  return function MaterialIcon({
    size = 20,
    className,
    style,
    strokeWidth,
    absoluteStrokeWidth,
    ...props
  }: IconProps) {
    void strokeWidth;
    void absoluteStrokeWidth;
    return (
      <span
        {...props}
        aria-hidden={props["aria-label"] ? undefined : true}
        className={["material-symbols-rounded", className].filter(Boolean).join(" ")}
        style={{
          width: size,
          height: size,
          fontSize: size,
          lineHeight: 1,
          ...style,
        } as CSSProperties}
      >
        {symbol}
      </span>
    );
  };
}

export const AlertCircle = materialIcon("error");
export const ArrowLeft = materialIcon("arrow_back");
export const ArrowRight = materialIcon("arrow_forward");
export const ArrowUpRight = materialIcon("north_east");
export const Bell = materialIcon("notifications");
export const Building2 = materialIcon("apartment");
export const CalendarDays = materialIcon("calendar_month");
export const Check = materialIcon("check");
export const ChevronDown = materialIcon("keyboard_arrow_down");
export const ChevronLeft = materialIcon("keyboard_arrow_left");
export const ChevronRight = materialIcon("keyboard_arrow_right");
export const Clock = materialIcon("schedule");
export const FileClock = materialIcon("history");
export const FileText = materialIcon("description");
export const FolderOpen = materialIcon("folder_open");
export const Handshake = materialIcon("handshake");
export const Inbox = materialIcon("inbox");
export const LayoutDashboard = materialIcon("dashboard");
export const LoaderCircle = materialIcon("autorenew");
export const LogOut = materialIcon("logout");
export const MapPin = materialIcon("location_on");
export const Menu = materialIcon("menu");
export const Pencil = materialIcon("edit");
export const Phone = materialIcon("call");
export const Plus = materialIcon("add");
export const RefreshCw = materialIcon("refresh");
export const Replace = materialIcon("swap_horiz");
export const Search = materialIcon("search");
export const Settings = materialIcon("settings");
export const ShieldCheck = materialIcon("verified_user");
export const Sparkles = materialIcon("auto_awesome");
export const Trash2 = materialIcon("delete_outline");
export const Users = materialIcon("groups");
export const X = materialIcon("close");
