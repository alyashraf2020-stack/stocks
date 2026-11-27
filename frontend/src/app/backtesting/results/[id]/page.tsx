import { BacktestDetail } from "@/components/BacktestingDashboard";
export default async function Page({ params }: PageProps<"/backtesting/results/[id]">) {
  const { id } = await params;
  return <BacktestDetail id={id} />;
}
