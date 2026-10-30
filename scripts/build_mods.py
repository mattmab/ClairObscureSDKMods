"""Build explicitly selected public mods with the matching SDK packager."""
import argparse
from pathlib import Path
import runpy
import sys
ROOT=Path(__file__).resolve().parents[1]
PUBLIC=('CatalogModels','Cinematics','ContinentFlight','E33WorldBuilder','EnemyHealth',
        'EnemySpawner','MapTravel','PictoEditor','SceneEditor','Statistics','WorldBuilderMapLoader')
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk',type=Path,required=True)
    parser.add_argument('--mod',action='append',choices=PUBLIC)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    sdk=args.sdk.resolve(strict=True)
    sys.path[:0]=[str(sdk/'src'),str(sdk/'scripts')]
    builder=runpy.run_path(str(sdk/'scripts/package_mods.py'))['build_all']
    builder(ROOT,args.output,include=set(args.mod or PUBLIC))
if __name__=='__main__':main()
