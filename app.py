import streamlit as st
import json
import math
import pandas as pd

st.set_page_config(page_title="Cloudera License Metric Calculator", layout="wide")

st.title("🧮 Cloudera CCU & DUM License Calculator")
st.markdown("Upload any Cloudera Manager export JSON (https://clouderamanager:7183/cmf/hardware/hosts/hostsOverview.json) to compute licensing targets and view floor condition alerts.")

uploaded_file = st.file_uploader("Upload Cluster Export File (.json)", type=["json"])

if uploaded_file is not None:
    try:
        data = json.load(uploaded_file)
        hosts = data.get('hosts', [])
        
        if not hosts:
            st.error("Invalid File Format: No hosts metadata array detected.")
        else:
            # 1. Base Variables
            total_nodes = len(hosts)
            cluster_name = hosts[0].get('clusterName', 'Generic Cluster')
            
            # Helper to profile hardware dynamically into neat clean buckets
            def classify_hardware(cores, mem_bytes, disk_bytes):
                mem_gib = mem_bytes / (1024**3)
                if cores == 64:
                    return "Worker Profile (64 Cores / 512GB RAM / 5.0TB Disk)"
                elif cores == 8:
                    return "Management Profile (8 Cores / 64GB RAM / 0.87TB Disk)"
                else:
                    return f"Custom Profile ({cores} Cores / {round(mem_gib)}GB RAM / {round(disk_bytes / 1e12, 1)}TB Disk)"

            # 2. Process Nodes & Groups
            rows = []
            group_counts = {}
            
            for h in hosts:
                cores = h.get('numCores', 0)
                mem_bytes = h.get('physicalMemoryTotal', 0)
                disk_bytes = h.get('diskTotal', 0)
                disk_used_bytes = h.get('diskUsed', 0)
                
                profile = classify_hardware(cores, mem_bytes, disk_bytes)
                group_counts[profile] = group_counts.get(profile, 0) + 1
                
                # Baseline nominal conversions for CCU
                mem_gib = mem_bytes / (1024**3)
                mem_nominal = 512 if mem_gib > 100 else 64
                
                # Compute CCU per node
                ccu_raw_calc = math.ceil((cores / 6) + (mem_nominal / 12))
                ccu_with_min_calc = max(ccu_raw_calc, 16)
                
                rows.append({
                    'Host': h.get('hostName'),
                    'Hardware Profile': profile,
                    'Cores': cores,
                    'Disk Total (TB)': round(disk_bytes / 1e12, 2),
                    'Disk Used (TB)': round(disk_used_bytes / 1e12, 2),
                    'Raw CCU': ccu_raw_calc,
                    'Adjusted CCU (Min 16)': ccu_with_min_calc,
                    'CCU Floor Triggered': 'Yes' if ccu_with_min_calc > ccu_raw_calc else 'No'
                })
                
            df_nodes = pd.DataFrame(rows)
            num_groups = len(group_counts)
            
            # 3. DISPLAY HEADER AND OVERALL CHARACTERISTICS
            st.markdown("---")
            st.header(f"📊 Cluster Metrics Report: **{cluster_name}**")
            
            st.markdown(f"**Total Number of Nodes:** {total_nodes}")
            st.markdown(f"**Number of Hardware Groups:** {num_groups}")
            for group_name, count in group_counts.items():
                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;🔹 **{group_name}:** {count} nodes")
            st.markdown("---")
            
            # 4. COMPUTE LICENSING METRICS WITH PRECISION BREAKDOWN
            st.subheader("⚙️ Licensing & Capacity Metrics")
            
            # CCU Aggregations
            total_ccu_raw = df_nodes['Raw CCU'].sum()
            total_ccu_with_min = df_nodes['Adjusted CCU (Min 16)'].sum()
            ccu_delta = total_ccu_with_min - total_ccu_raw
            
            # DUM Aggregations
            total_disk_capacity = df_nodes['Disk Total (TB)'].sum()
            total_disk_used = df_nodes['Disk Used (TB)'].sum()
            dum_threshold = total_nodes * 20.0
            dum_final = max(total_disk_capacity, dum_threshold)
            dum_delta = dum_final - total_disk_capacity
            
            # Side by side cards layout
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### 1. CCU (Cloudera Compute Units)")
                
                # Big Metric callout for final enforced license value
                st.metric(
                    label="Final Billable CCU (Enforced)", 
                    value=f"{total_ccu_with_min} CCU",
                    delta=f"+{ccu_delta} CCU from floor minimum" if ccu_delta > 0 else "Compliant (No Floor adjustment)",
                    delta_color="inverse" if ccu_delta > 0 else "normal"
                )
                
                # Detailed Precision Table
                ccu_table = pd.DataFrame({
                    "Metric Variant": ["Total CCU (With Minimum Enforced)", "Total CCU (Raw / Without Minimum)"],
                    "Value": [f"{total_ccu_with_min} CCU", f"{total_ccu_raw} CCU"],
                    "Status / Note": [
                        "⚠️ Minimum applied to Management nodes" if ccu_delta > 0 else "All nodes met threshold",
                        "Pure calculation before baseline correction"
                    ]
                })
                st.table(ccu_table)
                
            with col2:
                st.markdown("### 2. DUM (Data Under Management)")
                
                # Big Metric callout for final enforced license value
                st.metric(
                    label="Final Billable DUM (Enforced Floor)", 
                    value=f"{dum_final:.2f} TB",
                    delta=f"+{dum_delta:.2f} TB from cluster floor" if dum_delta > 0 else "Compliant (No Floor adjustment)",
                    delta_color="inverse" if dum_delta > 0 else "normal"
                )
                
                # Detailed Precision Table
                dum_table = pd.DataFrame({
                    "Metric Variant": [
                        "Total DUM Capacity (With Minimum Enforced)", 
                        "Total DUM Capacity (Raw / Without Minimum)", 
                        "Total DUM Actual Data Used"
                    ],
                    "Value": [
                        f"{dum_final:.2f} TB", 
                        f"{total_disk_capacity:.2f} TB", 
                        f"{total_disk_used:.2f} TB"
                    ],
                    "Status / Note": [
                        f"⚠️ Cluster-wide floor enforced ({total_nodes} nodes x 20TB)" if dum_delta > 0 else "Capacity exceeds minimum baseline",
                        "Sum of physical raw capacities across nodes",
                        "Actual utilized capacity for tracking reference"
                    ]
                })
                st.table(dum_table)
                
            # 5. DETAILED GRANULAR BREAKDOWN (Fixed index keyword crash)
            st.write("---")
            st.subheader("🔍 Individual Node Inventory Breakdown")
            # Removed index=False entirely to maintain backward-compatibility with older/newer Streamlit deployments safely
            st.dataframe(df_nodes, use_container_width=True)
            
            # Export capability
            csv = df_nodes.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Detailed Node Breakdown Report (CSV)",
                data=csv,
                file_name=f"{cluster_name.lower()}_license_breakdown.csv",
                mime="text/csv",
            )
            
    except Exception as e:
        st.error(f"An error occurred while parsing the cluster architecture: {str(e)}")
