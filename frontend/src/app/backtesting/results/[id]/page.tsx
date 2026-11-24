import { BacktestDetail } from "@/components/BacktestingDashboard";
export default function Page({ params }: { params: { id: string } }) {
  return <BacktestDetail id={params.id} />;
}
