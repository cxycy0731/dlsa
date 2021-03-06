from pyspark.sql.functions import col, when
from pyspark.sql import functions as F
from pyspark.ml.feature import StringIndexer, OneHotEncoder
from pyspark.ml import Pipeline
from pyspark.sql.window import Window
import sys


def get_sdummies(sdf, dummy_columns, keep_top, replace_with='zzz_other', dummy_info=[]):
    """Index string columns and group all observations that occur in less then a keep_top% of the rows in sdf per column.

    :param sdf: A pyspark.sql.dataframe.DataFrame
    :param dummy_columns: String columns that need to be indexed
    :param keep_top: List [1, 0.8, 0.8]
    :param replace_with: String to use as replacement for the observations that need to be grouped.

    return sdf, dummy_info
    """
    total = sdf.count()
    column_i = 0

    factor_set = {}  # The full dummy sets
    factor_selected = {}  # Used dummy sets
    factor_dropped = {}  # Dropped dummy sets
    factor_selected_names = {}  # Final revised factors

    for string_col in dummy_columns:

        if len(dummy_info) == 0:
            # Descending sorting with counts
            sdf_column_count = sdf.groupBy(string_col).count().orderBy(
                'count', ascending=False)
            sdf_column_count = sdf_column_count.withColumn(
                "cumsum",
                F.sum("count").over(Window.partitionBy().orderBy().rowsBetween(
                    -sys.maxsize, 0)))

            # Obtain top dummy factors
            sdf_column_top_dummies = sdf_column_count.withColumn(
                "cumperc", sdf_column_count['cumsum'] / total).filter(
                    col('cumperc') <= keep_top[column_i])
            keep_list = sdf_column_top_dummies.select(string_col).rdd.flatMap(
                lambda x: x).collect()

            # Save factor sets
            factor_set[string_col] = sdf_column_count.select(string_col).rdd.flatMap(
                lambda x: x).collect()
            factor_selected[string_col] = keep_list
            factor_dropped[string_col] = list(set(factor_set[string_col]) - set(keep_list))
            # factor_selected_names[string_col] = [string_col + '_' + str(x) for x in factor_new ]

        else:
            keep_list = dummy_info["factor_selected"][string_col]

        # Replace dropped dummy factors with grouped factors.
        sdf = sdf.withColumn(
            string_col,
            when((col(string_col).isin(keep_list)),
                 col(string_col)).otherwise(replace_with))

        # Apply string indexer
        pipeline = Pipeline(stages=[
            StringIndexer(inputCol=string_col, outputCol="IDX_" + string_col)
        ])
        sdf = pipeline.fit(sdf).transform(sdf)

        encoder = OneHotEncoder(inputCol="IDX_" + string_col,
                                outputCol="ONEHOT_" + string_col)
        encoder.setDropLast(True)  # only keep 2^n-n dummies to keep dummy independent.
        sdf = encoder.transform(sdf)

        column_i += 1

    # Drop intermediate columns
    drop_columns = ["IDX_" + x for x in dummy_columns]  # +  dummy_columns
    sdf = sdf.drop(*drop_columns)

    if len(dummy_info) == 0:
        dummy_info = {
            'factor_set': factor_set,
            'factor_selected': factor_selected,
            'factor_dropped': factor_dropped,
            'factor_selected_names': factor_selected_names
        }

    return sdf, dummy_info
