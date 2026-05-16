import re

with open(r'D:\stat-tools\pages\03_方差分析.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find and fix lines 1352-1389 (0-indexed: 1351-1388)
# Replace the broken loop body with correct indentation

new_lines = []
i = 0
while i < len(lines):
    if i == 1351 and lines[i].strip() == 'for env in environments:':
        # Found the loop start, replace the entire loop body until 'sp_df = pd.DataFrame'
        new_lines.append(lines[i])  # for env in environments:
        new_lines.append(lines[i+1])  # df_env = ...
        new_lines.append(lines[i+2])  # blank line
        new_lines.append(lines[i+3])  # if block_var_met is not None:
        new_lines.append(lines[i+4])  # formula_sp with block
        new_lines.append(lines[i+5])  # else:
        new_lines.append(lines[i+6])  # formula_sp without block
        new_lines.append('\n')
        # Add env_mean, env_std, env_cv, env_n
        new_lines.append('            env_mean = df_env[response].mean()\n')
        new_lines.append('            env_std = df_env[response].std()\n')
        new_lines.append("            env_cv = (env_std / env_mean * 100) if env_mean != 0 else 0\n")
        new_lines.append('            env_n = len(df_env)\n')
        new_lines.append('\n')
        new_lines.append('            try:\n')
        # Fix indentation: model_sp etc should be at 12 spaces (try body), not 16 (else body)
        for j in range(i+7, i+24):
            line = lines[j]
            stripped = line.strip()
            if stripped in ('', 'except Exception:'):
                new_lines.append(line)
            elif stripped.startswith('model_sp') or stripped.startswith('anova_sp') or stripped.startswith('geno_row') or stripped.startswith('for idx_name') or stripped.startswith('if genotype') or stripped.startswith('geno_row = anova_sp') or stripped.startswith('break') or stripped.startswith("f_val = geno_row") or stripped.startswith("p_val = geno_row") or stripped.startswith('geno_stats') or stripped.startswith('geno_max_mean') or stripped.startswith('geno_min_mean') or stripped.startswith('geno_range'):
                # Fix: change from 16 spaces to 12 spaces (try block level)
                if line.startswith('                '):
                    new_lines.append('            ' + line.lstrip())
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        # except line
        new_lines.append('            except Exception:\n')
        new_lines.append('                f_val, p_val, geno_range = np.nan, np.nan, np.nan\n')
        # Skip to single_point_results.append
        j = i + 24
        while j < len(lines) and 'single_point_results.append' not in lines[j]:
            j += 1
        for k in range(j, j+10):
            if k < len(lines):
                new_lines.append(lines[k])
        i = j + 10
    else:
        new_lines.append(lines[i])
        i += 1

with open(r'D:\stat-tools\pages\03_方差分析.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Done")
