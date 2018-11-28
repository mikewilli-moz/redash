import React from 'react';
import PropTypes from 'prop-types';
import { capitalize, map } from 'lodash';
import Select from 'antd/lib/select';

import { QueryData, Visualization } from '@/components/proptypes';
import visualizationRegistry from '@/visualizations/registry';
import VisualizationRenderer from './VisualizationRenderer';
import Filters from './Filters';

export default class VisualizationOptionsEditor extends React.Component {
  static propTypes = {
    // eslint-disable-next-line react/no-unused-prop-types
    visualization: Visualization.isRequired,
    updateVisualization: PropTypes.func.isRequired,
    data: QueryData.isRequired,
    setFilters: PropTypes.func.isRequired,
    filters: PropTypes.arrayOf(Filters.Filter).isRequired,
  }

  updateType = type => this.props.updateVisualization({
    ...this.props.visualization,
    type,
    name: this.props.visualization.name === visualizationRegistry[this.props.visualization.type].name ?
      visualizationRegistry[type].name :
      this.props.visualization.name,
    options: type !== this.props.visualization.type ?
      visualizationRegistry[type].defaultOptions :
      this.props.visualization.options,
  })

  updateName = e => this.props.updateVisualization({ ...this.props.visualization, name: e.target.value })
  updateOptions = newOptions => this.props.updateVisualization({
    ...this.props.visualization,
    options: {
      ...this.props.visualization.options,
      ...newOptions,
    },
  })

  render() {
    const Editor = visualizationRegistry[this.props.visualization.type].editor;
    return (
      <React.Fragment>
        <div className="col-md-5 p-r-10 p-l-0">
          <div className="form-group">
            <label className="control-label">Visualization Type</label>
            <Select
              value={this.props.visualization.type}
              disabled={this.props.visualization && !!this.props.visualization.id}
              onChange={this.updateType}
              className="form-control"
            >
              {map(visualizationRegistry, (v, t) => <Select.Option key={t}>{v.name}</Select.Option>)}
            </Select>
          </div>
          <div className="form-group">
            <label className="control-label">Visualization Name</label>
            <input
              name="name"
              type="text"
              className="form-control"
              value={this.props.visualization.name}
              placeholder={capitalize(this.props.visualization.type)}
              onChange={this.updateName}
            />
          </div>
          <Editor
            options={this.props.visualization.options}
            updateOptions={this.updateOptions}
            data={this.props.data}
            clientConfig={
            /* Can't include this in propTypes now since that will prevent react2angular from injecting it */
            /* eslint-disable-next-line react/prop-types */
            this.props.clientConfig}
          />
        </div>
        <div className="col-md-7 p-0 visualization-editor__right">
          <VisualizationRenderer
            filters={this.props.filters}
            setFilters={this.props.setFilters}
            data={this.props.data}
            visualization={this.props.visualization}
            updateOptions={this.updateOptions}
            clientConfig={
              /* eslint-disable-next-line react/prop-types */
              this.props.clientConfig}
          />
        </div>
      </React.Fragment>
    );
  }
}