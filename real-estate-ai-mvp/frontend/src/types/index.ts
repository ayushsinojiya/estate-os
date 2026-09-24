export type Entity = { id: string; [key: string]: any };
export type Page<T = Entity> = {
  items: T[];
  total: number;
  page: number;
  size: number;
};
export type Workspace = {
  id: string;
  name: string;
  role: "ADMIN" | "MANAGER" | "REAL_ESTATE_AGENT";
};
export type Session = {
  token: string;
  user: { id: string; name: string; email: string };
  workspaces: Workspace[];
};
export type Field = {
  name: string;
  label: string;
  type?: string;
  required?: boolean;
  options?: { value: string; label: string; parentValue?: string }[];
  dependsOn?: string;
  remote?: RemoteOptions;
  min?: number;
  max?: number;
  step?: string;
  wide?: boolean;
  hint?: string;
};
export type RemoteOptions = {
  path: string | ((values: Record<string, any>) => string);
  detailPath: string;
  label: (record: Entity) => string;
};
