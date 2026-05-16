import pandas as pd
import numpy as np
np.random.seed(42)

genotypes = ['郑单958','先玉335','京科968','中单909','登海605','联创808','华美1号','豫单9953']
environments = ['北京昌平','河南新乡','山东济南','河北石家庄','辽宁沈阳']
blocks = ['区组1','区组2','区组3']

geno_base = {'郑单958':680,'先玉335':710,'京科968':660,'中单909':700,'登海605':690,'联创808':675,'华美1号':685,'豫单9953':665}
env_effect = {'北京昌平':-10,'河南新乡':30,'山东济南':-5,'河北石家庄':15,'辽宁沈阳':-20}

rows = []
for g in genotypes:
    for e in environments:
        base = geno_base[g] + env_effect[e]
        for b_idx, b in enumerate(blocks):
            noise = np.random.normal(0, 15)
            block_eff = (b_idx - 1) * 5
            val = round(base + noise + block_eff, 1)
            rows.append({'品种':g,'地点':e,'区组':b,'产量':val})

df = pd.DataFrame(rows)
df.to_csv('data/区试试验示例数据.csv', index=False, encoding='utf-8-sig')
print(f'OK: {len(df)} rows, {df["品种"].nunique()} genotypes, {df["地点"].nunique()} sites')
