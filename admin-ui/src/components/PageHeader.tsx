interface Props {
  tag?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export default function PageHeader({ tag, title, description, action }: Props) {
  return (
    <div className="px-8 pt-8 pb-6 border-b border-[#1a1a1a]">
      {tag && <p className="section-tag mb-2">// {tag}</p>}
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight leading-none">{title}</h1>
          {description && <p className="text-sm text-[#555] mt-1.5">{description}</p>}
        </div>
        {action && <div className="flex-shrink-0">{action}</div>}
      </div>
    </div>
  );
}
