"""Public time thresholds, distinct from physics reference reproduction times."""
from urllib.parse import urlsplit

def set_goal(metadata, board, rank):
    if rank not in (1,10):raise ValueError('Only Top 1 and Top 10 targets are supported')
    if urlsplit(board['sourceUrl']).path!=f"/api/leaderboard/map/{metadata['mapUid']}":
        raise ValueError('Leaderboard belongs to another map')
    times={int(row['position']):int(row['time']) for row in board['tops']}
    if 1 not in times or 10 not in times or min(times.values())<=1 or times[1]>times[10]:
        raise ValueError('Missing/invalid public time thresholds')
    result=dict(metadata)
    result.update(top10TargetMs=times[10],worldBestMs=times[1],top1TargetMs=times[1]-1,
        targetRank=rank,targetMs=times[1]-1 if rank==1 else times[10],targetExclusive=rank==1,
        targetSourceUrl=board['sourceUrl'],targetFetchedUtc=board['fetchedUtc'])
    return result


def milestone(development,metadata):
    rows=development.get('trials',[])
    # The first common case is nominal; other development cases contain kicks.
    nominal=rows[0].get('finishMs') if rows else None
    top10=nominal is not None and nominal<=metadata.get('top10TargetMs',metadata['targetMs'])
    top1=nominal is not None and nominal<=metadata.get('top1TargetMs',metadata['referenceMs']-1)
    return {'top10ReachedOnNominalDevelopment':top10,'top1ReachedOnNominalDevelopment':top1,
        'phase':'top1_reached' if top1 else ('pursuing_top1' if top10 else 'pursuing_top10')}


def goal_for_rank(metadata,rank):
    if rank not in (1,10):raise ValueError('Only Top 1 and Top 10 targets are supported')
    result=dict(metadata)
    result.update(targetRank=rank,targetExclusive=rank==1,
        targetMs=metadata['top1TargetMs'] if rank==1 else metadata['top10TargetMs'])
    return result


def cached_goal_passed(result,metadata):
    """Recheck the complete nominal qualification against the requested rank."""
    if not result:return False
    if result.get('map',{}).get('mapUid')!=metadata['mapUid']:return False
    report=result.get('nominal64',{})
    if not report.get('count') or report.get('finishes')!=report['count']:return False
    worst=report.get('worstMs')
    return worst is not None and worst<=metadata['targetMs']
