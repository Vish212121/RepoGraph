export default function TenantSwitcher({ tenant, onChange }: { tenant: string; onChange: (value: string) => void }) {
  return (
    <label className="tenant-switcher">
      <span>Tenant</span>
      <select value={tenant} onChange={(event) => onChange(event.target.value)}>
        <option value="demo-alpha">demo-alpha</option>
        <option value="demo-beta">demo-beta</option>
      </select>
    </label>
  );
}
