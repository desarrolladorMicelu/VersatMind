interface Props {
  tag?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export default function PageHeader({ tag, title, description, action }: Props) {
  return (
    <header className="sticky top-0 z-20 border-b border-[var(--color-border-subtle)] bg-[var(--color-bg)]/85 px-6 pb-5 pt-16 backdrop-blur-xl sm:px-8 lg:pt-7">
      {tag && <p className="section-tag mb-2">{tag}</p>}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold leading-tight tracking-tight text-[var(--color-text)]">{title}</h1>
          {description && <p className="mt-1.5 text-sm text-[var(--color-text-muted)]">{description}</p>}
        </div>
        {action && <div className="flex-shrink-0">{action}</div>}
      </div>
    </header>
  );
}
